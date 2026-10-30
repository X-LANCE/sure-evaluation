# Broadband EDT MAE

Reports the absolute prediction/reference error of broadband EDT in seconds.
Each RIR uses its broadband onset, then each channel fits the full-band 0 to
-10 dB Schroeder decay and extrapolates that slope to 60 dB. Channel errors are
averaged per sample and samples are equally weighted.

This is distinct from `rir_edt_m_mae`: the latter averages 500 Hz and 1 kHz
octave-band EDT values before computing error. Broadband EDT has no ISO Table
A.1 frequency-band JND applied by this route.
