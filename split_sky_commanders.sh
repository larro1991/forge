#!/bin/bash
# Split Sky Commanders disc rips into individual episodes using silence-detected boundaries.
# Runs inside a container with ffmpeg + access to archive and staging.
#
# Disc layout (2 eps each, except Disc 5 which has 3):
#   Disc 1: E01, E02  |  Disc 2: E03, E04  |  Disc 3: E05, E06
#   Disc 4: E07, E08  |  Disc 5: E09, E10, E11  |  Disc 6: E12, E13

INPUT="/input"
OUTPUT="/output/Sky Commanders (1987)/Season 1"
SHOW="Sky Commanders (1987)"

mkdir -p "$OUTPUT"

# Episode titles (from TVDB)
E01="Assault on Raider Stronghold"
E02="Back in the Fold"
E03="Fresh Recruit"
E04="Marooned"
E05="Divide and Conquer"
E06="One on One"
E07="Rescuers Need Rescuing"
E08="Terminal Temblor"
E09="S.O.S."
E10="Turncoat"
E11="Deep Freeze"
E12="Firestorm"
E13="The Agony of Defeat"

split_2() {
    local disc="$1" split="$2" ep1_num="$3" ep1_title="$4" ep2_num="$5" ep2_title="$6"
    local src="$INPUT/SkyCommandersDisc${disc}.mp4"
    local out1="$OUTPUT/${SHOW} - S01E${ep1_num} - ${ep1_title}.mp4"
    local out2="$OUTPUT/${SHOW} - S01E${ep2_num} - ${ep2_title}.mp4"

    echo "=== Disc $disc: E${ep1_num} + E${ep2_num} (split at ${split}s) ==="

    echo "  Extracting E${ep1_num}..."
    ffmpeg -y -i "$src" -t "$split" -c copy -avoid_negative_ts make_zero "$out1" 2>/dev/null
    echo "  Extracting E${ep2_num}..."
    ffmpeg -y -i "$src" -ss "$split" -c copy -avoid_negative_ts make_zero "$out2" 2>/dev/null

    ls -lh "$out1" "$out2" 2>/dev/null
    echo ""
}

split_3() {
    local disc="$1" split1="$2" split2="$3"
    local ep1_num="$4" ep1_title="$5" ep2_num="$6" ep2_title="$7" ep3_num="$8" ep3_title="$9"
    local src="$INPUT/SkyCommandersDisc${disc}.mp4"
    local out1="$OUTPUT/${SHOW} - S01E${ep1_num} - ${ep1_title}.mp4"
    local out2="$OUTPUT/${SHOW} - S01E${ep2_num} - ${ep2_title}.mp4"
    local out3="$OUTPUT/${SHOW} - S01E${ep3_num} - ${ep3_title}.mp4"

    echo "=== Disc $disc: E${ep1_num} + E${ep2_num} + E${ep3_num} (splits at ${split1}s, ${split2}s) ==="

    echo "  Extracting E${ep1_num}..."
    ffmpeg -y -i "$src" -t "$split1" -c copy -avoid_negative_ts make_zero "$out1" 2>/dev/null
    echo "  Extracting E${ep2_num}..."
    ffmpeg -y -i "$src" -ss "$split1" -t "$(echo "$split2 - $split1" | bc)" -c copy -avoid_negative_ts make_zero "$out2" 2>/dev/null
    echo "  Extracting E${ep3_num}..."
    ffmpeg -y -i "$src" -ss "$split2" -c copy -avoid_negative_ts make_zero "$out3" 2>/dev/null

    ls -lh "$out1" "$out2" "$out3" 2>/dev/null
    echo ""
}

# Silence boundaries (silence_end = clean start of next episode):
# Disc 1: 1216.02   Disc 2: 1206.46   Disc 3: 1208.80
# Disc 4: 1238.12   Disc 5: 1246.75, 1879.09   Disc 6: 1278.92

split_2 1 1216.02  "01" "$E01" "02" "$E02"
split_2 2 1206.46  "03" "$E03" "04" "$E04"
split_2 3 1208.80  "05" "$E05" "06" "$E06"
split_2 4 1238.12  "07" "$E07" "08" "$E08"
split_3 5 1246.75 1879.09  "09" "$E09" "10" "$E10" "11" "$E11"
split_2 6 1278.92  "12" "$E12" "13" "$E13"

echo "=== All splits complete ==="
echo "Output files:"
ls -lh "$OUTPUT/"
echo ""
echo "Total: $(ls "$OUTPUT/" | wc -l) files"
