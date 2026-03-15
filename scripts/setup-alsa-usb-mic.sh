#!/bin/sh
# Set the USB microphone as ALSA default for capture only (playback stays on Pi).
# Run on the Raspberry Pi with:  sh setup-alsa-usb-mic.sh 1
# (Use the card number from 'arecord -l', e.g. card 1.)
CAPTURE_CARD="${1:-1}"
ASOUNDRC="${HOME}/.asoundrc"
cat > "$ASOUNDRC" << EOF
# Capture = USB mic (card $CAPTURE_CARD), playback = Pi (card 0) to avoid dmix errors
pcm.!default {
    type asym
    playback.pcm "plughw:0,0"
    capture.pcm "plughw:${CAPTURE_CARD},0"
}
ctl.!default {
    type hw
    card 0
}
EOF
echo "Wrote $ASOUNDRC: capture on card $CAPTURE_CARD, playback on card 0. Restart the server."
