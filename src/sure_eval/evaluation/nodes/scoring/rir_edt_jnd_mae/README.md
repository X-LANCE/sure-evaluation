# ISO 3382 EDT JND Error

Computes 500 Hz and 1 kHz EDT, averages those values per channel, and divides
the absolute error by 5% of the reference EDT. The score is the arithmetic mean
of channel JND multiples and is dimensionless (`x_jnd`). Reports also include
absolute MAE in seconds and the percentage of samples for which all channels
are within one JND. Mono, binaural, and larger multichannel inputs are
supported.

This is the informative ISO 3382-1 Annex A Table A.1 threshold applied as a
benchmark comparison. The standard does not prescribe channel averaging or a
model pass rate.
