# ISO 3382 C80 JND Error

Computes C80 in the 500 Hz and 1 kHz octave bands, averages per channel, and
normalizes the absolute error by the Table A.1 threshold of 1 dB. The score is
the mean channel error in `x_jnd`; the report retains absolute C80 MAE and
the within-one-JND sample percentage. Mono, binaural, and larger multichannel
inputs are supported.
