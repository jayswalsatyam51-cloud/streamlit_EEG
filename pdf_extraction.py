import pdfplumber
import json
import csv
import os
from collections import defaultdict
import time
import pandas as pd
import glob
import re

# Define the bands for each section
BANDS_MAPPING = {
    "Z Scored FFT Absolute Power": ["DELTA", "THETA", "ALPHA", "BETA", "HIGH BETA", "BETA 1", "BETA 2", "BETA 3"],
    "Z Scored FFT Power Ratio": ["D/T", "D/A", "D/B", "D/G", "T/A", "T/B", "T/G", "A/B", "A/G", "B/G"],
    "Z Scored Peak Frequency": ["DELTA", "THETA", "ALPHA", "BETA", "HIGH BETA", "BETA 1", "BETA 2", "BETA 3"],
    "Z Scored FFT Peak Frequency": ["DELTA", "THETA", "ALPHA", "BETA", "HIGH BETA", "BETA 1", "BETA 2", "BETA 3"],
    "Z Scored FFT Coherence": ["DELTA", "THETA", "ALPHA", "BETA"],
    "Z Scored FFT Phase Lag": ["DELTA", "THETA", "ALPHA", "BETA"]
}

# Define channel order
LEFT_CHANNELS = ['FP1 - LE', 'F3 - LE', 'C3 - LE', 'P3 - LE', 'O1 - LE', 'F7 - LE', 'T3 - LE', 'T5 - LE']
RIGHT_CHANNELS = ['FP2 - LE', 'F4 - LE', 'C4 - LE', 'P4 - LE', 'O2 - LE', 'F8 - LE', 'T4 - LE', 'T6 - LE']
CENTER_CHANNELS = ['Fz - LE', 'Cz - LE', 'Pz - LE']
HOMOLOGOUS_PAIRS = ['FP1 FP2', 'F3 F4', 'C3 C4', 'P3 P4', 'O1 O2', 'F7 F8', 'T3 T4', 'T5 T6']
ALL_CHANNELS = LEFT_CHANNELS + RIGHT_CHANNELS + CENTER_CHANNELS

def extract_coherence_phase_lag(pdf_paths):
    all_pdfs_data = []
    
    for pdf_path in pdf_paths:
        extracted_data = {
            "Z Scored FFT Coherence": {
                "LEFT": [],
                "RIGHT": [],
                "HOMOLOGOUS": []
            },
            "Z Scored FFT Phase Lag": {
                "LEFT": [],
                "RIGHT": [],
                "HOMOLOGOUS": []
            }
        }
        
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                lines = text.split('\n')
                current_section = None
                current_subsection = None
                in_homologous_section = False

                for line in lines:
                    line = line.strip()
                    
                    # Identify section headers
                    for section in ["Z Scored FFT Coherence", "Z Scored FFT Phase Lag"]:
                        if section in line:
                            current_section = section
                            current_subsection = None
                            in_homologous_section = False
                            break

                    # Detect subsections
                    if current_section:
                        if "Intrahemispheric: LEFT" in line:
                            current_subsection = "LEFT"
                            in_homologous_section = False
                            continue
                        elif "Intrahemispheric: RIGHT" in line:
                            current_subsection = "RIGHT"
                            in_homologous_section = False
                            continue
                        elif "Interhemispheric: HOMOLOGOUS PAIRS" in line:
                            current_subsection = "HOMOLOGOUS"
                            in_homologous_section = True
                            continue

                        # Process data lines
                        if current_subsection:
                            bands = BANDS_MAPPING[current_section]
                            parts = line.split()
                            
                            if len(parts) >= 6:  # Minimum length for a valid data line
                                # For LEFT and RIGHT sections, process both sides of the line
                                if current_subsection in ["LEFT", "RIGHT"]:
                                    mid_point = len(parts) // 2
                                    left_parts = parts[:mid_point]
                                    right_parts = parts[mid_point:]
                                    
                                    # Process left side
                                    if len(left_parts) >= 6:
                                        left_channel = f"{left_parts[0]} {left_parts[1]}"
                                        left_values = left_parts[2:6]
                                        try:
                                            numeric_values = [float(v) for v in left_values]
                                            for band, value in zip(bands, numeric_values):
                                                extracted_data[current_section]["LEFT"].append({
                                                    "Channel": left_channel,
                                                    "Band": band,
                                                    "Value": value
                                                })
                                        except ValueError:
                                            pass
                                    
                                    # Process right side
                                    if len(right_parts) >= 6:
                                        right_channel = f"{right_parts[0]} {right_parts[1]}"
                                        right_values = right_parts[2:6]
                                        try:
                                            numeric_values = [float(v) for v in right_values]
                                            for band, value in zip(bands, numeric_values):
                                                extracted_data[current_section]["RIGHT"].append({
                                                    "Channel": right_channel,
                                                    "Band": band,
                                                    "Value": value
                                                })
                                        except ValueError:
                                            pass
                                
                                # For HOMOLOGOUS section, process each line for multiple pairs
                                elif in_homologous_section:
                                    i = 0
                                    while i < len(parts) - 5:
                                        # Check if current and next part form a homologous pair
                                        pair = f"{parts[i]} {parts[i+1]}"
                                        if pair in HOMOLOGOUS_PAIRS:
                                            values = parts[i+2:i+6]
                                            try:
                                                numeric_values = [float(v) for v in values]
                                                if len(numeric_values) == len(bands):
                                                    for band, value in zip(bands, numeric_values):
                                                        extracted_data[current_section]["HOMOLOGOUS"].append({
                                                            "Channel": pair,
                                                            "Band": band,
                                                            "Value": value
                                                        })
                                            except ValueError:
                                                pass
                                            i += 6  # Move to next possible pair
                                        else:
                                            i += 1

        all_pdfs_data.append(extracted_data)
    
    return all_pdfs_data

def extract_other_sections(pdf_paths):
    # Dictionary to store data from all PDFs
    all_pdfs_data = []
    
    for pdf_path in pdf_paths:
        extracted_data = {
            "Z Scored FFT Absolute Power": [],
            "Z Scored FFT Power Ratio": [],
            "Z Scored Peak Frequency": [],
            "Z Scored FFT Peak Frequency": []
        }
        
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                lines = text.split('\n')
                current_section = None
                center_section = False

                for line in lines:
                    line = line.strip()
                    line_lower = line.lower()
                    # Identify section headers (robust matching)
                    for section in extracted_data.keys():
                        if section.lower() in line_lower:
                            current_section = section
                            center_section = False
                            print(f"Detected section: {section} in file {pdf_path}")
                            break

                    # Detect CENTER section
                    if "intrahemispheric: center" in line_lower:
                        center_section = True

                    # Process data lines
                    if current_section:
                        bands = BANDS_MAPPING[current_section]
                        # Use ALL_CHANNELS for robust channel detection
                        if any(channel in line for channel in ALL_CHANNELS):
                            channel = next(ch for ch in ALL_CHANNELS if ch in line)
                            values_str = line[line.find(channel) + len(channel):].strip()
                            # Use regex split for robust whitespace handling
                            values = re.split(r'\s+', values_str)
                            if current_section in ["Z Scored FFT Absolute Power", "Z Scored Peak Frequency", "Z Scored FFT Peak Frequency"]:
                                processed_values = []
                                for v in values:
                                    try:
                                        processed_values.append(float(v))
                                    except ValueError:
                                        continue
                                if len(processed_values) == len(bands):
                                    for band, value in zip(bands, processed_values):
                                        extracted_data[current_section].append({
                                            "Channel": channel,
                                            "Band": band,
                                            "Value": value
                                        })
                                else:
                                    print(f"Skipped line (wrong number of values): {line} | Got {len(processed_values)} values, expected {len(bands)}")
                            elif current_section == "Z Scored FFT Power Ratio":
                                try:
                                    numeric_values = [float(v) for v in values]
                                    if len(numeric_values) == len(bands):
                                        for band, value in zip(bands, numeric_values):
                                            extracted_data[current_section].append({
                                                "Channel": channel,
                                                "Band": band,
                                                "Value": value
                                            })
                                except ValueError:
                                    continue
                            continue

                        # Handle CENTER section
                        if center_section:
                            parts = line.split()
                            if parts and parts[0] in ['Fz', 'Cz', 'Pz']:
                                channel = f"{parts[0]} - LE"
                                values_str = line[line.find('- LE') + 4:].strip()
                                values = values_str.split()
                                try:
                                    numeric_values = [float(v) for v in values]
                                    if len(numeric_values) == len(bands):
                                        for band, value in zip(bands, numeric_values):
                                            extracted_data[current_section].append({
                                                "Channel": channel,
                                                "Band": band,
                                                "Value": value
                                            })
                                except ValueError:
                                    continue
                            continue

                        # Handle other regular channels (fallback)
                        parts = line.split()
                        if len(parts) > 1:
                            value_start = 1
                            while value_start < len(parts) and not parts[value_start].replace('.', '').replace('-', '').isdigit():
                                value_start += 1
                            channel = ' '.join(parts[:value_start])
                            values = parts[value_start:]
                            try:
                                numeric_values = [float(v) for v in values]
                                if len(numeric_values) == len(bands):
                                    for band, value in zip(bands, numeric_values):
                                        extracted_data[current_section].append({
                                            "Channel": channel,
                                            "Band": band,
                                            "Value": value
                                        })
                            except ValueError:
                                continue
        all_pdfs_data.append(extracted_data)
    return all_pdfs_data

def merge_data(all_pdfs_data):
    merged_data = defaultdict(list)
    
    for pdf_data in all_pdfs_data:
        for section, values in pdf_data.items():
            if section in ["Z Scored FFT Coherence", "Z Scored FFT Phase Lag"]:
                # Merge LEFT, RIGHT, and HOMOLOGOUS data
                for subsection in ["LEFT", "RIGHT", "HOMOLOGOUS"]:
                    for item in values[subsection]:
                        key = (section, subsection, item["Channel"], item["Band"])
                        merged_data[key].append(item["Value"])
            else:
                # Merge other sections
                for item in values:
                    key = (section, item["Channel"], item["Band"])
                    merged_data[key].append(item["Value"])
    
    # Convert merged data to final format
    final_data = {}
    for key, values in merged_data.items():
        if len(key) == 4:  # Coherence and Phase Lag
            section, subsection, channel, band = key
            if section not in final_data:
                final_data[section] = {"LEFT": [], "RIGHT": [], "HOMOLOGOUS": []}
            final_data[section][subsection].append({
                "Channel": channel,
                "Band": band,
                "Values": values
            })
        else:  # Other sections
            section, channel, band = key
            if section not in final_data:
                final_data[section] = []
            final_data[section].append({
                "Channel": channel,
                "Band": band,
                "Values": values
            })
    
    return final_data

def save_to_json(data, json_output_path):
    with open(json_output_path, 'w', encoding='utf-8') as json_file:
        json.dump(data, json_file, indent=4, ensure_ascii=False)

def save_to_csv(data, csv_output_path):
    # Create a CSV file for each section
    for section, values in data.items():
        section_csv_path = os.path.join(os.path.dirname(csv_output_path), f"{section}.csv")
        
        # Try to write the file with retries
        max_retries = 3
        retry_delay = 1  # seconds
        
        for attempt in range(max_retries):
            try:
                # If file exists, try to remove it first
                if os.path.exists(section_csv_path):
                    try:
                        os.remove(section_csv_path)
                    except PermissionError:
                        print(f"Waiting for file to be released: {section_csv_path}")
                        time.sleep(retry_delay)
                        continue
                
                with open(section_csv_path, 'w', newline='', encoding='utf-8') as csv_file:
                    writer = csv.writer(csv_file)
                    
                    # Write header for all sections
                    writer.writerow(['Subsection', 'Channel', 'Band', 'T1 Z', 'T2 Z', 'DZ', 'Normalize'])
                    
                    # Process all sections with subsections
                    if section in ["Z Scored FFT Coherence", "Z Scored FFT Phase Lag"]:
                        subsections = ["LEFT", "RIGHT", "HOMOLOGOUS"]
                        for subsection in subsections:
                            for item in values[subsection]:
                                process_and_write_row(writer, subsection, item)
                    else:
                        # For Absolute Power, Power Ratio, and Peak Frequency
                        # Group items by their channel type
                        left_items = []
                        right_items = []
                        center_items = []
                        
                        for item in values:
                            channel = item['Channel']
                            if any(ch in channel for ch in LEFT_CHANNELS):
                                left_items.append(item)
                            elif any(ch in channel for ch in RIGHT_CHANNELS):
                                right_items.append(item)
                            elif any(ch in channel for ch in CENTER_CHANNELS):
                                center_items.append(item)
                        
                        # Process each subsection
                        for subsection, items in [("LEFT", left_items), ("RIGHT", right_items), ("CENTER", center_items)]:
                            for item in items:
                                process_and_write_row(writer, subsection, item)
                
                break  # If successful, break the retry loop
                
            except PermissionError:
                if attempt < max_retries - 1:  # Don't sleep on the last attempt
                    print(f"Permission denied, retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    print(f"Failed to write to {section_csv_path} after {max_retries} attempts")
                    raise

def process_and_write_row(writer, subsection, item):
    # Ensure we have exactly 2 values (one from each PDF)
    values_list = item['Values']
    t1_value = abs(float(values_list[0])) if len(values_list) > 0 else ''
    t2_value = abs(float(values_list[1])) if len(values_list) > 1 else ''
    
    # Calculate DZ and Normalize
    if t1_value != '' and t2_value != '':
        dz = abs(t1_value - t2_value)
        if abs(dz) < 0.2 * t1_value:
            normalize = "NS"
        elif t2_value < t1_value:
            normalize = "Yes"
        else:
            normalize = "No"
    else:
        dz = ''
        normalize = ''
    
    writer.writerow([
        subsection,
        item['Channel'],
        item['Band'],
        t1_value,
        t2_value,
        dz,
        normalize
    ])

def process_csv(csv_path, section_type):
    df = pd.read_csv(csv_path)
    summary_rows = []

    if section_type in ["Z Scored FFT Coherence", "Z Scored FFT Phase Lag"]:
        # Group by Subsection and Band
        for subsection in df['Subsection'].unique():
            sub_df = df[df['Subsection'] == subsection]
            for band in sub_df['Band'].unique():
                band_df = sub_df[sub_df['Band'] == band]
                t1_sum = band_df['T1 Z'].abs().sum()
                t2_sum = band_df['T2 Z'].abs().sum()
                summary_rows.append({
                    'Subsection': subsection,
                    'Channel': 'Band-wise Breakup',
                    'Band': band,
                    'T1 Z': t1_sum,
                    'T2 Z': t2_sum,
                    'DZ': '',
                    'Normalize': ''
                })
    else:
        # Group by Channel type (LEFT, RIGHT, CENTER) if available, else just by Band
        for band in df['Band'].unique():
            band_df = df[df['Band'] == band]
            t1_sum = band_df['T1 Z'].abs().sum()
            t2_sum = band_df['T2 Z'].abs().sum()
            summary_rows.append({
                'Channel': 'Band-wise Breakup',
                'Band': band,
                'T1 Z': t1_sum,
                'T2 Z': t2_sum,
                'DZ': '',
                'Normalize': ''
            })

    # Append summary to CSV
    summary_df = pd.DataFrame(summary_rows)
    df = pd.concat([df, summary_df], ignore_index=True)
    df.to_csv(csv_path, index=False)
    print(f"Updated {csv_path} with band-wise absolute sums.")

def main():
    # Path to the directory where CSVs are saved
    csv_dir = "uploads"  # Change this to your output directory
    for csv_file in glob.glob(os.path.join(csv_dir, "**", "*.csv"), recursive=True):
        # Infer section type from filename
        if "Coherence" in csv_file:
            section_type = "Z Scored FFT Coherence"
        elif "Phase Lag" in csv_file:
            section_type = "Z Scored FFT Phase Lag"
        else:
            section_type = "Other"
        process_csv(csv_file, section_type)

# Instead, add this if you want to test the file directly
if __name__ == "__main__":
    print("This module is meant to be imported, not run directly.")
    print("Please use the FastAPI endpoint to process PDF files.")
    main()

