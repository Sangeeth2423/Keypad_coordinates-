#!/usr/bin/env python3

import re
import json
import time
import subprocess
from datetime import datetime

HARDWARE_FILE = "hardware.json"
OUTPUT_FILE = "keypad_coordinates.json"
LOG_FILE = "keypad_coordinates_log.json"


# ----------------------------------------
# Read hardware.json
# ----------------------------------------
def read_hardware_file():

    with open(HARDWARE_FILE, "r") as file:

        return file.read()


# ----------------------------------------
# Save JSON
# ----------------------------------------
def save_json_file(file_name, data):

    with open(file_name, "w") as file:

        json.dump(data, file, indent=4)


# ----------------------------------------
# Append log
# ----------------------------------------
def append_log(message):

    try:

        with open(LOG_FILE, "r") as log_file:

            logs = json.load(log_file)

    except:

        logs = []

    logs.append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "message": message
    })

    save_json_file(LOG_FILE, logs)

    print(
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    )


# ----------------------------------------
# Restart edge service
# ----------------------------------------

def restart_service(service_name):

    try:

        subprocess.run(
            [
                "sudo",
                "systemctl",
                "restart",
                service_name
            ],
            check=True
        )

        append_log(
            f"{service_name} restarted successfully"
        )

    except Exception as error:

        append_log(
            f"Failed to restart {service_name}: {error}"
        )


def check_edge_status():

    try:

        result = subprocess.run(
            [
                "sudo",
                "systemctl",
                "status",
                "edge-controller.service"
            ],
            capture_output=True,
            text=True
        )

        output = result.stdout + result.stderr

        append_log(output)

        if "Active: active (running)" in output:

            append_log(
                "Service status: Active (running)"
            )

            return True

        append_log(
            "Service status check failed"
        )

        return False

    except Exception as error:

        append_log(
            f"Status check failed: {error}"
        )

        return False


# ----------------------------------------
# Extract camera blocks
# ----------------------------------------
def extract_camera_blocks(content):

    pattern = (
        r'\{\s*"ID"\s*:\s*"[^"]+"'
        r'[\s\S]*?"URL"\s*:\s*"[^"]+"\s*,?\s*\}'
    )

    return re.findall(pattern, content)


# ----------------------------------------
# Extract KEYPAD_COORDS
# ----------------------------------------
def extract_keypad_data(content):

    output = []

    camera_blocks = extract_camera_blocks(content)

    for block in camera_blocks:

        id_match = re.search(
            r'"ID"\s*:\s*"([^"]+)"',
            block
        )

        name_match = re.search(
            r'"NAME"\s*:\s*"([^"]+)"',
            block
        )

        keypad_match = re.search(
            r'"KEYPAD_COORDS"\s*:\s*(\[[\s\S]*?\])',
            block
        )

        if (
            id_match
            and name_match
            and keypad_match
        ):

            try:

                keypad_coords = json.loads(
                    keypad_match.group(1)
                )

            except:

                continue

            output.append({

                "ID": id_match.group(1),

                "NAME": name_match.group(1),

                "KEYPAD_COORDS": keypad_coords
            })

    return output


# ----------------------------------------
# Format keypad coords
# Maintain exact alignment
# ----------------------------------------
def format_keypad_coords(coords):

    return f'''"KEYPAD_COORDS": [
                {{
                    "ENABLED": {str(coords[0]["ENABLED"]).lower()},
                    "TOP": {coords[0]["TOP"]},
                    "LEFT": {coords[0]["LEFT"]},
                    "WIDTH": {coords[0]["WIDTH"]},
                    "HEIGHT": {coords[0]["HEIGHT"]},
                    "AVG_BLUR": {coords[0]["AVG_BLUR"]}
                }}
            ],'''


# ----------------------------------------
# STEP 1
# Create keypad_coordinates.json
# ----------------------------------------

append_log("Creating keypad_coordinates.json")

hardware_content = read_hardware_file()



keypad_data = extract_keypad_data(
    hardware_content
)

save_json_file(
    OUTPUT_FILE,
    keypad_data
)

success_message = (
    "keypad_coordinates.json created successfully"
)

append_log(success_message)

camera_count_message = (
    f"Saved cameras count: {len(keypad_data)}"
)


append_log(camera_count_message)


# ----------------------------------------
# STEP 2
# Check every 30 seconds
# ----------------------------------------
while True:

    checking_message = (
        "Checking keypad coordinates..."
    )

    append_log(checking_message)

    hardware_content = read_hardware_file()

    updated = False

    # Reload keypad_coordinates.json
    with open(OUTPUT_FILE, "r") as file:

        keypad_data = json.load(file)

    # Check only saved cameras
    for saved_camera in keypad_data:

        saved_id = saved_camera["ID"]

        saved_name = saved_camera["NAME"]

        saved_coords = saved_camera["KEYPAD_COORDS"]

        formatted_coords = format_keypad_coords(
            saved_coords
        )

        # ----------------------------------------
        # Find exact camera block
        # ----------------------------------------
        camera_pattern = (
            r'(\{\s*"ID"\s*:\s*"'
            + re.escape(saved_id)
            + r'"[\s\S]*?"URL"\s*:\s*"[^"]+"\s*,?\s*\})'
        )

        camera_match = re.search(
            camera_pattern,
            hardware_content
        )

        if camera_match:

            current_block = camera_match.group(1)

            # ----------------------------------------
            # Already exists
            # ----------------------------------------
            if '"KEYPAD_COORDS"' in current_block:

                found_message = (
                    f"[FOUND] Camera {saved_id}"
                )

                append_log(found_message)

            else:

                # ----------------------------------------
                # Add coords with exact alignment
                # ----------------------------------------
                insert_text = (
                    '\n            '
                    + formatted_coords
                )

                updated_block = re.sub(
                    r'("ID"\s*:\s*"'
                    + re.escape(saved_id)
                    + r'"\s*,)',
                    r'\1'
                    + insert_text,
                    current_block
                )

                # Replace only exact block once
                hardware_content = re.sub(
                    re.escape(current_block),
                    lambda m: updated_block,
                    hardware_content,
                    count=1
                )

                updated = True

                added_message = (
                    f"Camera {saved_id} ({saved_name}) "
                    f"did not have KEYPAD_COORDS. "
                    f"Coordinates added successfully."
                )

                append_log(added_message)

    # ----------------------------------------
    # Save updated hardware.json
    # ----------------------------------------
    if updated:

        with open(HARDWARE_FILE, "w") as file:

            file.write(hardware_content)

        updated_message = (
            "hardware.json updated successfully"
        )

        append_log(updated_message)

        # ----------------------------------------
        # Restart edge service
        # ONLY when changes happen
        # ----------------------------------------
        append_log(
            "hardware.json saved successfully"
        )

        append_log(
            "Waiting 5 seconds before restart"
        )

        time.sleep(5)

        restart_message = (
            "Restarting edge-controller.service ..."
        )

        append_log(restart_message)

        restart_service(
            "edge-controller.service"
        )

        append_log(
            "Waiting 10 seconds before status check"
        )

        time.sleep(10)

        if check_edge_status():

            append_log(
                "Edge service healthy"
            )

        else:

            append_log(
                "Edge service unhealthy"
            )

            append_log(
                "Trying to re-insert KEYPAD_COORDS"
            )

            # Latest hardware.json read again
            hardware_content = read_hardware_file()

            # Re-insert only missing cameras
            for saved_camera in keypad_data:

                saved_id = saved_camera["ID"]

                saved_coords = saved_camera["KEYPAD_COORDS"]

                formatted_coords = format_keypad_coords(
                    saved_coords
                )

                camera_pattern = (
                    r'(\{\s*"ID"\s*:\s*"'
                    + re.escape(saved_id)
                    + r'"[\s\S]*?"URL"\s*:\s*"[^"]+"\s*,?\s*\})'
                )

                camera_match = re.search(
                    camera_pattern,
                    hardware_content
                )

                if camera_match:

                    append_log(
                        f"Checking camera {saved_id} during recovery"
                    )

                    current_block = camera_match.group(1)

                    if '"KEYPAD_COORDS"' not in current_block:

                        insert_text = (
                            '\n            '
                            + formatted_coords
                        )

                        updated_block = re.sub(
                            r'("ID"\s*:\s*"'
                            + re.escape(saved_id)
                            + r'"\s*,)',
                            r'\1' + insert_text,
                            current_block
                        )

                        hardware_content = re.sub(
                            re.escape(current_block),
                            lambda m: updated_block,
                            hardware_content,
                            count=1
                        )

            with open(HARDWARE_FILE, "w") as file:

                file.write(hardware_content)

            append_log(
                "KEYPAD_COORDS re-insert completed"
            )


            append_log(
                "Waiting 5 seconds before recovery restart"
            )

            time.sleep(5)

            restart_service(
                "edge-controller.service"
            )

            append_log(
                "Waiting 10 seconds after recovery restart"
            )

            time.sleep(10)

            if check_edge_status():

                append_log(
                    "Recovery successful"
                )

            else:

                append_log(
                    "Recovery failed"
                )

                append_log(
                    "KEYPAD_COORDS verified. "
                    "Edge service issue is not related to camera coordinates."
                )

                append_log(
                    "Continuing normal monitoring loop."
                )

    else:

        no_change_message = (
            "No changes needed"
        )

        append_log(no_change_message)

    # ----------------------------------------
    # Wait
    # ----------------------------------------
    wait_message = (
        "Waiting 30 seconds..."
    )

    append_log(wait_message)

    time.sleep(15)