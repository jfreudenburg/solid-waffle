""" Start with a realization of a perfect detector
1.  The mean charge <Q_a(i,j)> = It_a
2.  Realization of a 4096 x 4096 pixel^2 grid with 66 time samples
This final result data cube will then be [4k, 4k, 66] in dimensions
and will require some kind of identifying header, currently taken
from one of the DCL flats.  This is charge.
3.  Convert to ADU/DN via gain ~ number(e-)/counts;  set ~ FWD/2^16

Run tests with 128x128 or something small...
current I is per pixel (units: e/s)
time t (units: s)
time step for read from t_a to t_a+1 (will need to check # for convergence)

NOTE: to run this, one needs a copy of a DCL flat file with the name
set below.
"""
import sys
import numpy as np
from numpy.random import randn,poisson
import astropy.io.fits as fits
import fitsio
from fitsio import FITS,FITSHDR

# data cube attributes
nx, ny = 4096, 4096
#nx, ny = 128, 128
tsamp = 66
I = 2.0 # arbitrary scalar for now (e/s/pixel)
delta_tsamp = 3.0 # arbitrary for now (s)
nt_step = tsamp*3 # number of tot timesteps depending on convergence needs
delta_t = (delta_tsamp*tsamp)/nt_step # time between timesteps
allQ = np.zeros((nt_step, nx, ny))
data_cube_Q = np.zeros((tsamp, nx, ny))
data_cube_S = np.zeros_like(data_cube_Q)
gain = 1.5 # arbitrary scalar e-/DN

# Start with 0 charge in the first frame (t=0)
for tdx in range(1, nt_step):
    mean = I*delta_t
    # Create realization of charge
    # Seems to use up loads of memory, is there a better way?
    allQ[tdx,:,:] = allQ[tdx-1,:,:]+np.random.poisson(
        mean, allQ[tdx,:,:].shape)

# Sample tsamp times
data_cube_Q = allQ[::(nt_step/tsamp),:,:]
data_cube_S = np.array(data_cube_Q/gain, dtype=np.uint16)

# Open up an example DCL flat file and save the data cube
dclfile = 'Set_001_Test_0002.fits'
fitsio.write(dclfile, data_cube_S, clobber=True)

# Mean of a given slice checks out
# data_cube[1,:,:].mean()
# Try compression of data cube into file
# DCL file saved in 16-bit unsigned integers (look at header)
# End of script

"""
Things planned:
 * offset & clipping
 * reference pixels (4 around edge for all but WFC3 which has 5)
 * generate flats and darks
 * use real dark cube as read noise is reasonable, won't do hot pixels correctly, but ok for now
 * multiply I by quantum efficiency 
"""
