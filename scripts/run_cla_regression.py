#!/usr/bin/env python3
"""Run CLA Regression Testing - Multiple Evaluation Runs with Heatmap Analysis.

This script:
1. Runs lightspeed-eval N times with CLA test configs
2. Saves each run to timestamped directories (under CLA_REGRESSION)
3. Automatically generates heatmaps showing score changes over time

Usage:
    # Run 3 times and generate heatmaps
    python scripts/run_cla_regression.py --num-runs 3

    # Run 5 times with custom output directory
    python scripts/run_cla_regression.py --num-runs 5 --base-dir cla_regression_output

    # Run and only generate heatmaps (skip line plots)
    python scripts/run_cla_regression.py --num-runs 3 --plot-types heatmap

    # Run with custom configs
    python scripts/run_cla_regression.py --num-runs 3 \\
        --system-config config/system_cla.yaml \\
        --eval-data config/CLA_tests.yaml
"""

import argparse
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def run_single_evaluation(
    system_config: Path,
    eval_data: Path,
    output_dir: Path,
    run_number: int,
    total_runs: int,
) -> bool:
    """Run a single evaluation and save to timestamped directory.

    Args:
        system_config: Path to system config YAML
        eval_data: Path to evaluation data YAML
        output_dir: Base output directory
        run_number: Current run number (1-indexed)
        total_runs: Total number of runs

    Returns:
        True if successful, False otherwise
    """
    # Create timestamped directory name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = output_dir / f"full_suite_{timestamp}"

    print(f"\n{'='*80}")
    print(f"RUN {run_number}/{total_runs} - {timestamp}")
    print(f"{'='*80}")

    # Create subdirectory for this test config
    test_config_name = eval_data.stem  # e.g., "CLA_tests" from "CLA_tests.yaml"
    test_output_dir = run_dir / test_config_name
    test_output_dir.mkdir(parents=True, exist_ok=True)

    print(f"📁 Output directory: {test_output_dir}")
    print(f"🔧 System config: {system_config}")
    print(f"📋 Eval data: {eval_data}")
    print(f"\n⏳ Running evaluation...")

    # Run lightspeed-eval
    cmd = [
        "lightspeed-eval",
        "--system-config", str(system_config),
        "--eval-data", str(eval_data),
        "--output-dir", str(test_output_dir),
        "--cache-warmup",
    ]

    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=False,  # Show output in real-time
            text=True,
        )

        print(f"\n✅ Run {run_number}/{total_runs} completed successfully")
        return True

    except subprocess.CalledProcessError as e:
        print(f"\n❌ Run {run_number}/{total_runs} failed with exit code {e.returncode}")
        return False
    except FileNotFoundError:
        print("\n❌ Error: 'lightspeed-eval' command not found")
        print("   Make sure the package is installed: uv sync")
        return False


def run_all_evaluations(
    system_config: Path,
    eval_data: Path,
    output_dir: Path,
    num_runs: int,
    delay_between_runs: int = 2,
) -> int:
    """Run multiple evaluations sequentially.

    Args:
        system_config: Path to system config YAML
        eval_data: Path to evaluation data YAML
        output_dir: Base output directory
        num_runs: Number of runs to execute
        delay_between_runs: Seconds to wait between runs

    Returns:
        Number of successful runs
    """
    print(f"🚀 Starting CLA Regression Testing")
    print(f"{'='*80}")
    print(f"System config: {system_config}")
    print(f"Eval data: {eval_data}")
    print(f"Number of runs: {num_runs}")
    print(f"Output directory: {output_dir}")
    print(f"{'='*80}")

    # Create base output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    successful_runs = 0
    failed_runs = 0

    start_time = time.time()

    for run_num in range(1, num_runs + 1):
        success = run_single_evaluation(
            system_config,
            eval_data,
            output_dir,
            run_num,
            num_runs,
        )

        if success:
            successful_runs += 1
        else:
            failed_runs += 1

        # Wait between runs (except after last run)
        if run_num < num_runs and delay_between_runs > 0:
            print(f"\n⏸️  Waiting {delay_between_runs} seconds before next run...")
            time.sleep(delay_between_runs)

    elapsed_time = time.time() - start_time     # timestamp tag for folder - no this should be in the function that creates

    # Summary
    print(f"\n{'='*80}")
    print(f"EVALUATION RUNS COMPLETE")
    print(f"{'='*80}")
    print(f"✅ Successful: {successful_runs}/{num_runs}")
    print(f"❌ Failed: {failed_runs}/{num_runs}")
    print(f"⏱️  Total time: {elapsed_time:.1f} seconds ({elapsed_time/60:.1f} minutes)")
    print(f"📁 All results saved in: {output_dir}")

    return successful_runs


def generate_heatmaps(
    base_dir: Path,
    plot_types: list[str],
    system_config: Path,
    min_runs: int = 2,
) -> bool:
    """Call plot_scores_over_time.py to generate visualizations.

    Args:
        base_dir: Base directory containing evaluation runs
        plot_types: List of plot types to generate
        system_config: Path to system config (for thresholds)
        min_runs: Minimum runs required for plotting

    Returns:
        True if successful, False otherwise
    """
    print(f"\n{'='*80}")
    print(f"GENERATING HEATMAPS AND VISUALIZATIONS")
    print(f"{'='*80}")

    # Check if plot script exists
    script_dir = Path(__file__).parent
    plot_script = script_dir / "plot_scores_over_time.py"

    if not plot_script.exists():
        print(f"❌ Error: Plot script not found at {plot_script}")
        return False

    # Build command
    cmd = [
        "python",
        str(plot_script),
        "--base-dir", str(base_dir),
        "--min-runs", str(min_runs),
        "--plot-types", *plot_types,
    ]

    print(f"📊 Running: {' '.join(cmd)}")

    try:
        subprocess.run(cmd, check=True)
        print(f"\n✅ Visualizations generated successfully")
        return True

    except subprocess.CalledProcessError as e:
        print(f"\n❌ Visualization generation failed with exit code {e.returncode}")
        return False


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run CLA regression testing with multiple evaluation runs and heatmap analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run 3 times and generate heatmaps
  python scripts/run_cla_regression.py --num-runs 3

  # Run 5 times with only heatmaps (no line plots)
  python scripts/run_cla_regression.py --num-runs 5 --plot-types heatmap

  # Run with custom configs
  python scripts/run_cla_regression.py --num-runs 3 \\
      --system-config config/system_custom.yaml \\
      --eval-data config/custom_tests.yaml

  # Run without generating plots (just collect data)
  python scripts/run_cla_regression.py --num-runs 3 --skip-plots
        """,
    )

    parser.add_argument(
        "--num-runs",
        type=int,
        default=3,
        help="Number of evaluation runs to execute (default: 3)",
    )
    parser.add_argument(
        "--system-config",
        type=Path,
        default=Path("config/system_cla.yaml"),
        help="Path to system configuration file (default: config/system_cla.yaml)",
    )
    parser.add_argument(
        "--eval-data",
        type=Path,
        default=Path("config/CLA_tests.yaml"),
        help="Path to evaluation data file (default: config/CLA_tests.yaml)",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path("CLA_REGRESSION/eval_output"),
        help="Base directory for storing evaluation runs (default: eval_output)",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=2,
        help="Seconds to wait between runs (default: 2)",
    )
    parser.add_argument(
        "--plot-types",
        type=str,
        nargs="+",
        default=["heatmap"],
        choices=["line", "heatmap", "boxplot", "trend", "faceted", "all"],
        help="Types of plots to generate (default: heatmap). Use 'all' for all types.",
    )
    parser.add_argument(
        "--skip-plots",
        action="store_true",
        help="Skip plot generation (only run evaluations)",
    )
    parser.add_argument(
        "--min-runs",
        type=int,
        default=2,
        help="Minimum runs required for plotting (default: 2)",
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.system_config.exists():
        print(f"❌ Error: System config not found: {args.system_config}")
        return 1

    # todo: dont need - remove check - possibly need? idk test now = TODO
    if not args.eval_data.exists():
        print(f"❌ Error: Evaluation data not found: {args.eval_data}")
        return 1

    if args.num_runs < 1:
        print(f"❌ Error: Number of runs must be at least 1 (got {args.num_runs})")
        return 1

    # Run evaluations
    successful_runs = run_all_evaluations(
        args.system_config,
        args.eval_data,
        args.base_dir,
        args.num_runs,
        args.delay,
    )

    # Check if we have enough successful runs
    if successful_runs == 0:
        print("\n❌ All evaluation runs failed - cannot generate plots")
        return 1

    # Generate plots (unless skipped)
    if not args.skip_plots:
        if successful_runs < args.min_runs:
            print(f"\n⚠️  Warning: Only {successful_runs} successful run(s), need at least {args.min_runs} for plotting")
            print("   Skipping plot generation")
        else:
            success = generate_heatmaps(
                args.base_dir,
                args.plot_types,
                args.system_config,
                args.min_runs,
            )
            if not success:
                print("\n⚠️  Plot generation failed, but evaluation data is still available")
                print(f"   You can manually generate plots later with:")
                print(f"   python scripts/plot_scores_over_time.py --base-dir {args.base_dir}")

    # Final summary
    print(f"\n{'='*80}")
    print(f"✅ CLA REGRESSION TESTING COMPLETE")
    print(f"{'='*80}")
    print(f"\nResults:")
    print(f"  📁 Evaluation runs: {args.base_dir}/full_suite_*/")
    if not args.skip_plots and successful_runs >= args.min_runs:
        print(f"  📊 Visualizations: analysis_output/time_series/")
        print(f"  🔥 Heatmaps: analysis_output/time_series/heatmap_*.png")
    print(f"\nNext steps:")
    print(f"  # View heatmaps")
    print(f"  ls analysis_output/time_series/heatmap_*.png")
    print(f"  # View summary")
    print(f"  cat analysis_output/time_series/time_series_summary.txt")
    print(f"  # Re-generate plots with different options")
    print(f"  python scripts/plot_scores_over_time.py --base-dir {args.base_dir} --plot-types all")

    return 0 if successful_runs > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
