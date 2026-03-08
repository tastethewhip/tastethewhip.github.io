import csv

def sort_csv_by_column(input_file, output_file, column_name):
    # Read CSV into a list of dictionaries
    with open(input_file, mode='r', newline='', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        data = list(reader)

        if column_name not in reader.fieldnames:
            raise ValueError(f"Column '{column_name}' not found in CSV headers.")

    # Sort data by the specified column
    sorted_data = sorted(data, key=lambda row: row[column_name])

    # Write sorted data to a new CSV file
    with open(output_file, mode='w', newline='', encoding='utf-8') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=reader.fieldnames)
        writer.writeheader()
        writer.writerows(sorted_data)

    print(f"CSV sorted by '{column_name}' and saved to '{output_file}'.")

# Example usage
if __name__ == "__main__":
    input_csv = '2026inew.csv'          # Replace with your input file
    output_csv = '2026_part_i.csv' # Replace with your desired output file
    sort_column = 'date'             # Replace with the column to sort by

    try:
        sort_csv_by_column(input_csv, output_csv, sort_column)
    except Exception as e:
        print(f"Error: {e}")
