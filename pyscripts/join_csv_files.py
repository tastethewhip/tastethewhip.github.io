import csv
import os

def combine_csv_files(input_files, output_file):
    """
    Combines multiple CSV files into one, keeping only the header of the first file.

    Args:
        input_files (list): List of input CSV file paths.
        output_file (str): Path to the output CSV file.
    """
    if not input_files:
        print("No input files provided.")
        return
    
    with open(output_file, mode='w', newline='', encoding='utf-8') as outfile:
        writer = None
        for idx, file in enumerate(input_files):
            with open(file, mode='r', encoding='utf-8') as infile:
                reader = csv.reader(infile)
                header = next(reader)  # Read the header from the current file
                
                # Initialize the writer with the header from the first file
                if idx == 0:
                    writer = csv.writer(outfile)
                    writer.writerow(header)
                
                # Write the remaining rows
                for row in reader:
                    writer.writerow(row)
    
    print(f"Combined files saved to {output_file}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Combine multiple CSV files into one.")
    parser.add_argument(
        "input_files", nargs="+", help="Paths to input CSV files to be combined."
    )
    parser.add_argument(
        "--output", required=True, help="Path to the output CSV file."
    )

    args = parser.parse_args()

    if any(not os.path.exists(file) for file in args.input_files):
        print("One or more input files do not exist.")
    else:
        combine_csv_files(args.input_files, args.output)
