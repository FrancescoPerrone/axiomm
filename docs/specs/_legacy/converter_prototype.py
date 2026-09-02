# MIT License
#
# Copyright (c) 2025 Francesco Perrone
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# Special Clause for Joshua Franz Einsle:
# In recognition of the scientific contributions and collaborative efforts provided by
# Josh, the principal investigator and main collaborator on the scientific aspects
# of this project, he is granted a special non-exclusive, royalty-free usage right.
# Any derivative works or scientific publications that utilize the Software must
# explicitly acknowledge Josh's contributions by including his name, affiliation,
# and role as the primary scientific collaborator.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""
Diagnostic Cell for Processing Map Files with Metadata Extraction and Multiple-File Options

This cell:
1. Prompts the user to enter the sample identifier (e.g., "A21_054").
2. Opens a GUI dialog to select the maps directory.
3. Lists all .h5 files in the directory whose filenames contain the sample identifier.
4. Asks the user whether to process a single file or all matching files.
5. For each file to be processed, the user can choose to process it, skip it, or abort.
6. For each processed file, the cell:
   - Creates an output directory.
   - Loads the .h5 file.
   - Extracts configuration settings and energy regions.
   - Retrieves the counts dataset and creates a HyperSpy Signal1D.
   - Extracts shape information to compute xdim and ydim.
   - Attempts to extract the beam size from the configuration to determine pixel scale.
   - Updates the signal's axes metadata.
   - Saves the signal as a .hspy file.
"""

import os
import h5py
import hyperspy.api as hs
import pandas as pd
import tkinter as tk
from tkinter import filedialog

def process_file(map_path, sample, output_root):
    """Process a single .h5 file and save as .hspy with metadata."""
    print(f"\nProcessing file: {map_path}")
    # Open file
    try:
        data = h5py.File(map_path, 'r')
        print("H5 file loaded successfully.")
    except Exception as e:
        print(f"Error loading H5 file: {e}")
        return

    # Extract configuration settings
    try:
        config_names = pd.DataFrame(data['/xrmmap/config/environ/name'][:])
        config_values = pd.DataFrame(data['/xrmmap/config/environ/value'][:])
        config_df = pd.concat([config_names, config_values], axis=1)
        config_df = config_df.apply(lambda x: x.str.decode('utf-8') if isinstance(x[0], bytes) else x, axis=0)
        print("\nConfiguration settings:")
        print(config_df)
    except Exception as e:
        print(f"Error extracting configuration settings: {e}")

    # Extract energy regions
    try:
        lines = data['/xrmmap/config/rois/name'][()]
        limits = data['/xrmmap/config/rois/limits'][()]
        line_names = [element.decode('utf-8').replace('\x00', '') for element in lines]
        regions = pd.DataFrame(line_names, columns=['Line'])
        regions['Start'] = limits[:, 0] / 100
        regions['End'] = limits[:, 1] / 100
        print("\nEnergy regions:")
        print(regions)
    except Exception as e:
        print(f"Error extracting energy regions: {e}")

    # Retrieve counts dataset and create HyperSpy signal
    dataset_path = '/xrmmap/mcasum/counts'
    if dataset_path not in data:
        print(f"Dataset '{dataset_path}' not found in file.")
        return
    try:
        xrf_data = hs.signals.Signal1D(data[dataset_path])
        print("\nHyperSpy Signal created successfully.")
    except Exception as e:
        print(f"Error creating HyperSpy signal: {e}")
        return

    # Extract shape and compute xdim and ydim
    shape = data[dataset_path].shape
    if len(shape) < 3:
        print("Unexpected data shape; expected at least 3 dimensions.")
        return
    xdim = shape[0]
    ydim = shape[1]
    print(f"\nSignal shape: {shape} (xdim={xdim}, ydim={ydim})")

    # Extract beam size from configuration for dynamic scaling
    try:
        beam_size_str = config_df.loc[config_df[0] == 'Experiment.Beam_Size__Nominal', 1].values[0]
        beam_size = float(beam_size_str.lower().replace("um", "").strip())
        print(f"\nExtracted beam size from config: {beam_size} µm")
    except Exception as e:
        print(f"Could not extract beam size: {e}\nUsing fallback spatial scale (500/xdim).")
        beam_size = None

    # Determine navigation axis scale
    nav_scale = beam_size if beam_size is not None else 500 / xdim

    # Update axes metadata
    try:
        xrf_data.axes_manager.navigation_axes[0].name = 'x'
        xrf_data.axes_manager.navigation_axes[0].units = '\u03bcm'
        xrf_data.axes_manager.navigation_axes[0].scale = nav_scale

        xrf_data.axes_manager.navigation_axes[1].name = 'y'
        xrf_data.axes_manager.navigation_axes[1].units = '\u03bcm'
        xrf_data.axes_manager.navigation_axes[1].scale = nav_scale

        xrf_data.axes_manager.signal_axes[0].name = 'Energy'
        xrf_data.axes_manager.signal_axes[0].units = 'KeV'
        xrf_data.axes_manager.signal_axes[0].scale = 40.96 / 4096

        print("\nUpdated Axes Manager info:")
        print(xrf_data.axes_manager)
    except Exception as e:
        print(f"Error updating axes metadata: {e}")

    # Define output filename based on file name and sample
    map_name = os.path.splitext(os.path.basename(map_path))[0]
    output_directory = os.path.join(output_root, sample, map_name)
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)
        print(f"Created output directory: {output_directory}")
    else:
        print(f"Output directory already exists: {output_directory}")
    output_file = os.path.join(output_directory, f"{sample}_map.hspy")

    # Save the HyperSpy signal
    print(f"\nSaving HyperSpy signal to: {output_file}")
    try:
        xrf_data.save(output_file)
        print(f"Successfully saved HyperSpy signal to {output_file}")
    except Exception as e:
        print(f"Error saving HyperSpy signal: {e}")

# ================================
# Main Interactive Section
# ================================

# Prompt user for the sample identifier.
sample = input("Enter the sample identifier (e.g., A21_054): ").strip()
if not sample:
    raise ValueError("Sample identifier cannot be empty.")

# Use a GUI dialog to select the maps directory.
root = tk.Tk()
root.withdraw()
maps_directory = filedialog.askdirectory(title="Select the Maps Directory")
if not maps_directory:
    raise ValueError("No directory selected for maps.")
print(f"Selected Maps directory: {os.path.abspath(maps_directory)}")

# List all .h5 files in the selected directory containing the sample identifier.
files_in_directory = os.listdir(maps_directory)
files_for_sample = [f for f in files_in_directory if f.endswith('.h5') and sample in f]
if not files_for_sample:
    raise FileNotFoundError(f"No .h5 files containing '{sample}' were found in {maps_directory}.")

print("\nFiles found for sample:")
for f in files_for_sample:
    print(f)

# Ask user if they want to process a single file or all files.
process_option = input("\nProcess (1) a single file or (2) all files? (Enter 1 or 2): ").strip()
if process_option not in ['1', '2']:
    print("Invalid option. Exiting.")
    exit()

# Set the project output root as the current working directory.
project_path = os.getcwd()

if process_option == '1':
    # Process a single file.
    file_choice = input("Enter the exact filename to process (or 'q' to quit): ").strip()
    if file_choice.lower() == 'q':
        print("User interrupted processing. Exiting.")
        exit()
    if file_choice not in files_for_sample:
        print(f"File '{file_choice}' not found in the list. Exiting.")
        exit()
    map_path = os.path.join(maps_directory, file_choice)
    process_file(map_path, sample, project_path)
else:
    # Process all files.
    confirm_all = input(f"Process all {len(files_for_sample)} files? (y/n): ").strip().lower()
    if confirm_all != 'y':
        print("User aborted processing of all files. Exiting.")
        exit()
    for f in files_for_sample:
        # Ask user for each file if they want to process it or skip.
        choice = input(f"\nProcess file '{f}'? (y/n or 'q' to quit): ").strip().lower()
        if choice == 'q':
            print("User aborted processing. Exiting.")
            break
        elif choice == 'y':
            map_path = os.path.join(maps_directory, f)
            process_file(map_path, sample, project_path)
        else:
            print(f"Skipping file '{f}'.")
