"""
Batch processor module - handles batch file processing.
Single responsibility: Batch processing coordination and monitoring.
"""

import pandas as pd
from datetime import datetime
import traceback
import os


def process_file_batch(file_list, s3_client, config, filename_creator_func,
                       processing_func, event_name, save_metadata=True,
                       save_csv=True, verbose=True, **kwargs):
    """
    Process a batch of files.

    Args:
        file_list: List of files to process
        s3_client: S3 client
        config: Processing configuration
        filename_creator_func: Function to create output filenames
        processing_func: Function to process each file
        event_name: Event name
        save_metadata: Save metadata
        save_csv: Save results to CSV
        verbose: Print progress
        **kwargs: Additional arguments for processing function

    Returns:
        DataFrame: Processing results
    """
    results = []
    total_files = len(file_list)

    # Setup output directory
    local_output_dir = config.get('local_output_dir', f"output/{event_name}")
    os.makedirs(local_output_dir, exist_ok=True)

    if verbose:
        print(f"✅ Local output directory ready: {local_output_dir}")

    # Process each file
    for idx, file_path in enumerate(file_list, 1):
        print(f"\n[{idx}/{total_files}] Processing: {file_path}")

        # Create output filename
        output_filename = filename_creator_func(file_path, event_name)
        print(f"   Output filename: {output_filename}")

        # Record start time
        start_time = datetime.now()

        try:
            # Process the file
            processing_func(
                name=file_path,
                BUCKET=config['raw_data_bucket'],
                cog_filename=output_filename,
                cog_data_bucket=config['cog_data_bucket'],
                cog_data_prefix=config['cog_data_prefix'],
                s3_client=s3_client,
                local_output_dir=local_output_dir,
                **kwargs
            )

            # Record success
            processing_time = (datetime.now() - start_time).total_seconds()
            results.append({
                'original_file': file_path,
                'output_file': output_filename,
                'status': 'success',
                'processing_time_s': processing_time,
                'timestamp': datetime.now().isoformat()
            })

            print(f"   ✅ Generated and saved COG: {output_filename}")

        except FileExistsError:
            # File was skipped
            results.append({
                'original_file': file_path,
                'output_file': output_filename,
                'status': 'skipped',
                'processing_time_s': 0,
                'timestamp': datetime.now().isoformat(),
                'note': 'File already exists in S3'
            })
            print(f"   ⏭️ Skipped (already exists): {output_filename}")

        except Exception as e:
            # Record failure
            processing_time = (datetime.now() - start_time).total_seconds()
            results.append({
                'original_file': file_path,
                'output_file': output_filename,
                'status': 'failed',
                'error': str(e),
                'processing_time_s': processing_time,
                'timestamp': datetime.now().isoformat()
            })

            print(f"   ❌ Error processing {file_path}: {e}")
            if verbose:
                traceback.print_exc()

    # Create results DataFrame
    results_df = pd.DataFrame(results)

    # Save results if requested
    if save_csv and not results_df.empty:
        csv_filename = f"{local_output_dir}/processing_results_{event_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        results_df.to_csv(csv_filename, index=False)
        print(f"\n📊 Results saved to: {csv_filename}")

    return results_df


def process_single_file(file_path, s3_client, config, processing_func, verbose=True):
    """
    Process a single file.

    Args:
        file_path: Path to file
        s3_client: S3 client
        config: Processing configuration
        processing_func: Processing function
        verbose: Print progress

    Returns:
        dict: Processing result
    """
    start_time = datetime.now()

    try:
        result = processing_func(
            file_path=file_path,
            s3_client=s3_client,
            config=config
        )

        return {
            'file': file_path,
            'status': 'success',
            'result': result,
            'processing_time_s': (datetime.now() - start_time).total_seconds()
        }

    except Exception as e:
        return {
            'file': file_path,
            'status': 'failed',
            'error': str(e),
            'processing_time_s': (datetime.now() - start_time).total_seconds()
        }


def monitor_batch_progress(results_df, print_details=True):
    """
    Monitor batch processing progress.

    Args:
        results_df: DataFrame with results
        print_details: Print detailed statistics

    Returns:
        dict: Summary statistics
    """
    if results_df is None or results_df.empty:
        return {'total': 0}

    stats = {
        'total': len(results_df)
    }

    if 'status' in results_df.columns:
        status_counts = results_df['status'].value_counts()
        for status, count in status_counts.items():
            stats[status] = count

        stats['success_rate'] = (stats.get('success', 0) / stats['total']) * 100

    if 'processing_time_s' in results_df.columns:
        stats['total_time_minutes'] = results_df['processing_time_s'].sum() / 60
        stats['avg_time_seconds'] = results_df['processing_time_s'].mean()

    if print_details:
        print("\n" + "="*60)
        print("BATCH PROCESSING SUMMARY")
        print("="*60)
        for key, value in stats.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.2f}")
            else:
                print(f"  {key}: {value}")
        print("="*60)

    return stats


def generate_batch_metadata(results_df, config, event_name):
    """
    Generate metadata for batch processing.

    Args:
        results_df: DataFrame with results
        config: Processing configuration
        event_name: Event name

    Returns:
        dict: Batch metadata
    """
    metadata = {
        'event_name': event_name,
        'processing_date': datetime.now().isoformat(),
        'configuration': config,
        'statistics': monitor_batch_progress(results_df, print_details=False)
    }

    if results_df is not None and not results_df.empty:
        # Add file lists
        if 'status' in results_df.columns:
            for status in results_df['status'].unique():
                files = results_df[results_df['status'] == status]['original_file'].tolist()
                metadata[f'files_{status}'] = files

    return metadata