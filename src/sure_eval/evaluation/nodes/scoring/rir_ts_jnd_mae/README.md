# ISO 3382 Centre-Time JND Error

Computes energy-weighted centre time (`Ts`) in the 500 Hz and 1 kHz octave
bands, averages per channel, and normalizes the absolute error by the Table A.1
threshold of 10 ms. The score is the mean channel error in `x_jnd`; the report
retains absolute Ts MAE and the within-one-JND sample percentage. Mono,
binaural, and larger multichannel inputs are supported.
