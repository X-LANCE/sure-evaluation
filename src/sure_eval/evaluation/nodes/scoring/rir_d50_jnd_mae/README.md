# ISO 3382 D50 JND Error

Computes D50 in the 500 Hz and 1 kHz octave bands, averages per channel, and
normalizes the absolute error by the Table A.1 threshold of 0.05. The score is
the mean channel error in `x_jnd`; the report retains absolute D50 MAE and
the within-one-JND sample percentage. Mono, binaural, and larger multichannel
inputs are supported.
