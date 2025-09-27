"""
Parallel batch processor for COG conversion.
Processes multiple files simultaneously using multiprocessing.
Optimized for 4-core system with 24.7GB RAM.
"""

import os
import time
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime
from dataclasses import dataclass
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import queue
import logging
from tqdm import tqdm

# Import our optimized GDAL processor
from core.gdal_cog_processor import create_cog_gdal, process_file_optimized, set_optimal_gdal_env
from core.s3_operations import (
    check_s3_file_exists,
    download_from_s3,
    upload_to_s3,
    get_file_size_from_s3
)
from utils.error_handling import cleanup_temp_files
from utils.logging import print_status


# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ProcessingTask:
    """Single file processing task."""
    input_path: str
    output_path: str
    output_key: str
    bucket: str
    cog_bucket: str
    filename: str
    nodata: Optional[float] = None
    file_size_gb: float = 0
    overwrite: bool = False
    task_id: int = 0


class ParallelCOGProcessor:
    """
    Parallel COG processor optimized for batch operations.
    Uses multiprocessing for CPU-bound tasks and threading for I/O.
    """

    def __init__(self, s3_client, max_workers: int = 3, use_gdal: bool = True):
        """
        Initialize parallel processor.

        Args:
            s3_client: Boto3 S3 client
            max_workers: Maximum parallel workers (default 3 for 4-core system)
            use_gdal: Use GDAL COG driver (True) or fallback method (False)
        """
        self.s3_client = s3_client
        self.max_workers = max_workers
        self.use_gdal = use_gdal

        # Statistics
        self.stats = {
            'total': 0,
            'completed': 0,
            'failed': 0,
            'skipped': 0,
            'total_time': 0,
            'total_size_gb': 0
        }

        # Setup optimal GDAL environment
        os.environ.update(set_optimal_gdal_env())

    def process_batch(
        self,
        tasks: List[ProcessingTask],
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        Process multiple files in parallel.

        Args:
            tasks: List of processing tasks
            verbose: Print progress

        Returns:
            Dictionary with results and statistics
        """
        if not tasks:
            return {'results': [], 'stats': self.stats}

        self.stats['total'] = len(tasks)
        start_time = time.time()

        if verbose:
            print(f"\n{'='*60}")
            print(f"🚀 Parallel COG Processing")
            print(f"   Files: {len(tasks)}")
            print(f"   Workers: {self.max_workers}")
            print(f"   Method: {'GDAL COG Driver' if self.use_gdal else 'Fallback'}")
            print(f"{'='*60}\n")

        # Process files in parallel
        results = self._process_parallel(tasks, verbose)

        # Calculate statistics
        self.stats['total_time'] = time.time() - start_time
        throughput = self.stats['total_size_gb'] / (self.stats['total_time'] / 3600)  # GB/hour

        if verbose:
            print(f"\n{'='*60}")
            print(f"✅ Batch Processing Complete")
            print(f"   Total: {self.stats['total']} files")
            print(f"   Completed: {self.stats['completed']}")
            print(f"   Failed: {self.stats['failed']}")
            print(f"   Skipped: {self.stats['skipped']}")
            print(f"   Time: {self.stats['total_time']:.1f} seconds")
            print(f"   Throughput: {throughput:.1f} GB/hour")
            print(f"{'='*60}\n")

        return {
            'results': results,
            'stats': self.stats
        }

    def _process_parallel(self, tasks: List[ProcessingTask], verbose: bool) -> List[Dict]:
        """
        Process tasks in parallel using ProcessPoolExecutor.
        """
        results = []

        # Use ProcessPoolExecutor for CPU-bound COG creation
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_task = {}
            for task in tasks:
                future = executor.submit(self._process_single_file, task)
                future_to_task[future] = task

            # Process results as they complete
            with tqdm(total=len(tasks), desc="Processing files") as pbar:
                for future in as_completed(future_to_task):
                    task = future_to_task[future]
                    try:
                        result = future.result(timeout=300)  # 5-minute timeout
                        results.append(result)

                        # Update statistics
                        if result['status'] == 'success':
                            self.stats['completed'] += 1
                            self.stats['total_size_gb'] += task.file_size_gb
                        elif result['status'] == 'skipped':
                            self.stats['skipped'] += 1
                        else:
                            self.stats['failed'] += 1

                        pbar.update(1)

                        if verbose and result['status'] == 'success':
                            print(f"   ✓ {task.filename} ({task.file_size_gb:.1f} GB) in {result['time']:.1f}s")

                    except Exception as e:
                        logger.error(f"Task failed: {e}")
                        self.stats['failed'] += 1
                        results.append({
                            'file': task.filename,
                            'status': 'failed',
                            'error': str(e),
                            'time': 0
                        })
                        pbar.update(1)

        return results

    def _process_single_file(self, task: ProcessingTask) -> Dict:
        """
        Process a single file (runs in separate process).
        """
        start_time = time.time()
        temp_files = []

        try:
            # Check if file already exists
            if not task.overwrite:
                if check_s3_file_exists(self.s3_client, task.cog_bucket, task.output_key):
                    return {
                        'file': task.filename,
                        'status': 'skipped',
                        'reason': 'Already exists',
                        'time': time.time() - start_time
                    }

            # Download or stream file
            input_path = self._get_input_path(task)
            if not input_path:
                raise Exception("Failed to access input file")

            # Create temporary output path
            temp_output = f"/tmp/gdal_tmp/cog_{task.task_id}_{task.filename}"
            os.makedirs(os.path.dirname(temp_output), exist_ok=True)
            temp_files.append(temp_output)

            # Process with GDAL COG driver
            if self.use_gdal:
                success = process_file_optimized(
                    input_path,
                    temp_output,
                    nodata=task.nodata,
                    file_size_gb=task.file_size_gb,
                    reproject=True,
                    verbose=False
                )
            else:
                # Fallback to original method
                from main_processor import convert_to_cog
                convert_to_cog(
                    task.input_path,
                    task.bucket,
                    task.filename,
                    task.cog_bucket,
                    os.path.dirname(task.output_key),
                    self.s3_client,
                    manual_nodata=task.nodata,
                    overwrite=task.overwrite
                )
                success = True

            if not success:
                raise Exception("COG creation failed")

            # Upload to S3
            if not upload_to_s3(self.s3_client, temp_output, task.cog_bucket, task.output_key):
                raise Exception("Failed to upload to S3")

            return {
                'file': task.filename,
                'status': 'success',
                'output_key': task.output_key,
                'time': time.time() - start_time
            }

        except Exception as e:
            logger.error(f"Error processing {task.filename}: {e}")
            return {
                'file': task.filename,
                'status': 'failed',
                'error': str(e),
                'time': time.time() - start_time
            }

        finally:
            # Cleanup
            cleanup_temp_files(*temp_files)

    def _get_input_path(self, task: ProcessingTask) -> Optional[str]:
        """
        Get input path - either VSI path for streaming or download.
        """
        # Try streaming first
        vsi_path = f"/vsis3/{task.bucket}/{task.input_path}"

        # Test if VSI works
        import subprocess
        result = subprocess.run(
            ['gdalinfo', vsi_path],
            capture_output=True,
            timeout=10
        )

        if result.returncode == 0:
            return vsi_path

        # Fallback to download
        local_path = f"/tmp/gdal_tmp/input_{task.task_id}_{os.path.basename(task.input_path)}"
        os.makedirs(os.path.dirname(local_path), exist_ok=True)

        if download_from_s3(self.s3_client, task.bucket, task.input_path, local_path):
            return local_path

        return None


def create_tasks_from_file_list(
    file_list: List[str],
    bucket: str,
    cog_bucket: str,
    cog_prefix: str,
    filename_creator,
    event_name: str,
    s3_client,
    nodata: Optional[float] = None,
    overwrite: bool = False
) -> List[ProcessingTask]:
    """
    Create processing tasks from file list.
    """
    tasks = []

    for idx, file_path in enumerate(file_list):
        # Generate output filename
        cog_filename = filename_creator(file_path, event_name)
        output_key = f"{cog_prefix}/{cog_filename}"

        # Get file size
        try:
            file_size_gb = get_file_size_from_s3(s3_client, bucket, file_path)
        except:
            file_size_gb = 0

        task = ProcessingTask(
            input_path=file_path,
            output_path=cog_filename,
            output_key=output_key,
            bucket=bucket,
            cog_bucket=cog_bucket,
            filename=cog_filename,
            nodata=nodata,
            file_size_gb=file_size_gb,
            overwrite=overwrite,
            task_id=idx
        )
        tasks.append(task)

    return tasks


def process_files_parallel(
    file_list: List[str],
    product_name: str,
    output_dir: str,
    event_name: str,
    s3_client,
    bucket: str,
    cog_bucket: str,
    filename_creator,
    manual_nodata: Optional[float] = None,
    overwrite: bool = False,
    max_workers: int = 3
) -> Dict[str, Any]:
    """
    Main entry point for parallel processing.
    """
    if not file_list:
        return {'results': [], 'stats': {}}

    print(f"\n{'='*60}")
    print(f"🚀 Parallel Processing: {product_name}")
    print(f"{'='*60}")

    # Create tasks
    cog_prefix = f"drcs_activations_new/{output_dir}"
    tasks = create_tasks_from_file_list(
        file_list,
        bucket,
        cog_bucket,
        cog_prefix,
        filename_creator,
        event_name,
        s3_client,
        nodata=manual_nodata,
        overwrite=overwrite
    )

    # Initialize processor
    processor = ParallelCOGProcessor(
        s3_client,
        max_workers=max_workers,
        use_gdal=True
    )

    # Process batch
    results = processor.process_batch(tasks, verbose=True)

    # Save results to CSV
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_file = f"output/{event_name}/parallel_results_{product_name}_{timestamp}.csv"
    os.makedirs(os.path.dirname(results_file), exist_ok=True)

    with open(results_file, 'w') as f:
        import csv
        writer = csv.DictWriter(f, fieldnames=['file', 'status', 'time', 'error'])
        writer.writeheader()
        writer.writerows(results['results'])

    print(f"\n📊 Results saved to: {results_file}")

    return results


if __name__ == "__main__":
    # Example usage
    print("Parallel COG Processor ready for use")
    print("Import and use process_files_parallel() for batch processing")