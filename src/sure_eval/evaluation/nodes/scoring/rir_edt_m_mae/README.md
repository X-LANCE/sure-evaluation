# RIR Octave-Band EDT MAE

Computes EDT independently in the 500 Hz and 1 kHz octave bands, averages the
two band values for each channel, and reports the absolute prediction/reference
error in seconds. Channel and sample aggregation are arithmetic means.

The onset is the first broadband sample within 20 dB of the RIR peak. Filtering
uses a sixth-order Butterworth prototype with zero-phase filtering; the node
does not claim IEC 61260 certification. EDT fits the initial 0 to -10 dB
Schroeder decay and extrapolates the slope to 60 dB.

The metric runs in process and requires `sure-evaluation[audio]` for SoundFile
and SciPy. No model or checkpoint is used.
