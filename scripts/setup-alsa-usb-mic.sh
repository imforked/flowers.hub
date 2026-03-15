#!/bin/sh
# Set the USB microphone as the ALSA default so the wake word listener can use it.
# Run on the Raspberry Pi. Use the card number from 'arecord -l' (e.g. card 1).
CARD="${1:-1}"
ASOUNDRC="${HOME}/.asoundrc"
printf "defaults.pcm.card %s\ndefaults.ctl.card %s\n" "$CARD" "$CARD" > "$ASOUNDRC"
echo "Wrote $ASOUNDRC with card $CARD. Restart the server and try again."
