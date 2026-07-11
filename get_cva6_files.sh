#!/bin/bash

# Destination directory name
DEST_DIR="cva6_files"

# Create the destination directory if it doesn't exist
mkdir -p "$DEST_DIR"

# Define base paths
CVA6_REPO_DIR=$(pwd)
HPDCACHE_DIR="$CVA6_REPO_DIR/core/cache_subsystem/hpdcache"

echo "Starting file copy to $DEST_DIR..."
echo "CVA6_REPO_DIR = $CVA6_REPO_DIR"
echo "HPDCACHE_DIR = $HPDCACHE_DIR"
echo "------------------------------------------------"

# Function to process and copy files from a list
process_list() {
    local list_file=$1

    if [ ! -f "$list_file" ]; then
        echo "Error: File $list_file not found"
        return
    fi

    echo "Processing $list_file..."

    while IFS= read -r line; do
        # Remove leading and trailing whitespaces
        line=$(echo "$line" | xargs)

        # Ignore empty lines, comments (//), and directives from other manifests (-F)
        if [[ -z "$line" || "$line" == //* || "$line" == -F* ]]; then
            continue
        fi

        # Replace variables with absolute paths
        local path_str="${line//\$\{CVA6_REPO_DIR\}/$CVA6_REPO_DIR}"
        path_str="${path_str//\$\{HPDCACHE_DIR\}/$HPDCACHE_DIR}"

        # Logic for include directories (+incdir+)
        if [[ "$path_str" == +incdir+* ]]; then
            # Extract only the path by removing the '+incdir+' prefix
            local inc_dir="${path_str#+incdir+}"

            if [ -d "$inc_dir" ]; then
                echo "  Copying headers from: $inc_dir"
                # Use find to search for and copy only relevant files without recursion
                find "$inc_dir" -maxdepth 1 -type f \( -name "*.sv" -o -name "*.v" -o -name "*.svh" -o -name "*.vh" -o -name "*.h" \) -exec cp {} "$DEST_DIR/" \;
            else
                echo "  [Warning] +incdir+ directory not found: $inc_dir"
            fi

        # Logic for individual files
        else
            if [ -f "$path_str" ]; then
                cp "$path_str" "$DEST_DIR/"
            else
                echo "  [Warning] File not found: $path_str"
            fi
        fi
    done < "$list_file"
}

# Process both lists using their exact paths
process_list "$CVA6_REPO_DIR/core/Flist.cva6"
process_list "$HPDCACHE_DIR/rtl/hpdcache.Flist"

echo "------------------------------------------------"
echo "Process completed. Check the '$DEST_DIR' directory."