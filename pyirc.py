import numpy
import scipy
import astropy
from astropy.io import fits
import scipy.stats
import scipy.ndimage
import fitsio
from fitsio import FITS,FITSHDR

# <== THESE FUNCTIONS DEPEND ON THE FORMAT OF THE INPUT FILES ==>

# Version number of script
def get_version():
  return 4

# Function to get array size from format codes in load_segment
# (Note: for WFIRST this will be 4096, but we want the capability to
# run this script on H1/H2RG data.)
#
def get_nside(formatpars):
  if formatpars==1: return 4096
  if formatpars==2: return 2048
  if formatpars==3: return 4096

# Get number of time slices
def get_num_slices(formatpars, filename):

  # Switch based on input format
  if formatpars==1 or formatpars==2:
    hdus = fits.open(filename)
    ntslice = int(hdus[0].header['NAXIS3'])
    hdus.close()
  elif formatpars==3:
    hdus = fits.open(filename)
    ntslice = len(hdus)-1
    hdus.close()
  else:
    print 'Error! Invalid formatpars =', formatpars
    exit()
  return ntslice

# Function to load an image segment
#
# filename = name of the source FITS file
# formatpars = integer describing which type of format to use
#     format 1: H4RG, all data in a single HDU, ramp slope positive (ex. DCL H4RG-18237 data)
# xyrange = list [xmin,xmax,ymin,ymax] (first row/col are zero) -- EXcluding xmax and ymax!
# tslices = list of time slices to use (first is *1*)
# verbose = True or False (use True only for de-bugging)
#
# Returns a 3D array of dimension number tslices, ymax-ymin, xmax-xmin
#
def load_segment(filename, formatpars, xyrange, tslices, verbose):
  if verbose: print 'Reading:', filename

  # Recommended True (False defaults to astropy tools, which work but are slow because of the way this script works)
  use_fitsio = True

  # Get dimensions of output cube
  nxuse = xyrange[1]-xyrange[0]
  nyuse = xyrange[3]-xyrange[2]
  ntslice_use = len(tslices)
  output_cube = numpy.zeros((ntslice_use, nyuse, nxuse))

  # Switch based on input format
  if formatpars==1 or formatpars==2:
    if use_fitsio:
      fileh = fitsio.FITS(filename)
      N = get_nside(formatpars)
      for ts in range(ntslice_use):
        t = tslices[ts]
        output_cube[ts,:,:] = 65535 - numpy.array(fileh[0][t-1, xyrange[2]:xyrange[3], xyrange[0]:xyrange[1]])
      fileh.close()
    else:
      hdus = fits.open(filename)
      in_hdu = hdus[0]
      ntslice = in_hdu.data.shape[0]
      if verbose:
        print 'input shape -> ', in_hdu.data.shape
        print 'number of slices =', ntslice, ', used =', ntslice_use
      for ts in range(ntslice_use):
        t = tslices[ts]
        output_cube[ts,:,:] = 65535 - in_hdu.data[t-1, xyrange[2]:xyrange[3], xyrange[0]:xyrange[1]]
      hdus.close()
  elif formatpars==3:
    if use_fitsio:
      fileh = fitsio.FITS(filename)
      N = get_nside(formatpars)
      for ts in range(ntslice_use):
        t = tslices[ts]
        output_cube[ts,:,:] = numpy.array(fileh[t][xyrange[2]:xyrange[3], xyrange[0]:xyrange[1]])
      fileh.close()
    else:
      print 'Error: non-fitsio methods not yet supported for formatpars=3'
      exit()
  else:
    print 'Error! Invalid formatpars =', formatpars
    exit()

  return output_cube

# <== FUNCTIONS BELOW HERE ARE INDEPENDENT OF THE INPUT FORMAT ==>

# Routine to get percentile cuts with a mask removed
#
# mask consists of 0's and 1's and is the same size as this_array
def pyIRC_percentile(this_array, mask, perc):
  val = this_array.flatten()
  ma = mask.flatten()
  w = numpy.array([val[x] for x in numpy.where(ma>.5)])
  return numpy.percentile(w,perc)

# Routine to get mean with a mask removed
def pyIRC_mean(this_array, mask):
  val = this_array.flatten()
  ma = mask.flatten()
  w = numpy.array([val[x] for x in numpy.where(ma>.5)])
  return numpy.mean(w)

# Get reference corrections from left & right pixel sets
# yrange = [ymin,ymax] (inclusive)
#
# Output depends on the length of tslices:
#  elements 0 .. ntslice_use-1 -> median of that time slice
#  elements ntslice_use .. 2*ntslice_use-1 -> median of (first) - (this slice)
#  (if ntslice_use>=2) then
#    element 2*ntslice_use -> median of [(-2) - (-1)] - [(0) - (1)] (otherwise this is 0)
#    [this is really used to measure curvature of the reference pixel ramp]
#
# output always has length 2*ntslice_use+1
#
def ref_corr(filename, formatpars, yrange, tslices, verbose):

  # Side length of the array (needed to find reference pixel indexing)
  N = get_nside(formatpars)
  # Number of time slices
  ntslice_use = len(tslices)
  # Clear list
  output_ref = []

  # Build arrays of reference pixels
  my_array_L = load_segment(filename, formatpars, [0,4]+yrange, tslices, False)
  my_array_R = load_segment(filename, formatpars, [N-4,N]+yrange, tslices, False)
  my_array_LR = numpy.concatenate((my_array_L, my_array_R), axis=2)
  if verbose: print N, my_array_LR.shape

  for ts in range(ntslice_use):
    output_ref.append(numpy.median(my_array_LR[ts,:,:]))
  for ts in range(ntslice_use):
    diff_array = my_array_LR[0,:,:] - my_array_LR[ts,:,:]
    output_ref.append(numpy.median(diff_array))
  if ntslice_use>1:
    diff_array = my_array_LR[ntslice_use-2,:,:] - my_array_LR[ntslice_use-1,:,:]\
                 -(my_array_LR[0,:,:]-my_array_LR[1,:,:])*(tslices[-1]-tslices[-2])/float(tslices[1]-tslices[0])
    output_ref.append(numpy.median(diff_array))
  else:
    output_ref.append(0)
  return output_ref

#
# Get reference corrections from left & right pixel sets
# for a full list of files.
# ny = number of y-bins (e.g. 32 for an H4RG and regions of 128 pixel size in y-direction)
#
# Output depends on the length of tslices:
#  elements 0 .. ntslice_use-1 -> median of that time slice
#  elements ntslice_use .. 2*ntslice_use-1 -> median of (first) - (this slice)
#  (if ntslice_use>=2) then
#    element 2*ntslice_use -> median of [(-2) - (-1)] - [(0) - (1)] (otherwise this is 0)
#    [this is really used to measure curvature of the reference pixel ramp]
#
# output is stored in a numpy array of size num_files, ny, 2*ntslice_use+1
#
def ref_array(filelist, formatpars, ny, tslices, verbose):

  num_files = len(filelist)
  ntslice_use = len(tslices)
  output_array = numpy.zeros((num_files, ny, 2*ntslice_use+1))

  dy = get_nside(formatpars)//ny
  for ifile in range(num_files):
    for iy in range(ny):
      ymin = dy*iy
      ymax = ymin+dy
      output_array[ifile, iy, :] = numpy.asarray(ref_corr(filelist[ifile], formatpars, [ymin,ymax], tslices, False))
      if verbose:
        print ifile, iy
        print output_array[ifile, iy, :]

  return(output_array)
#
# Similar but if we only need one row (iy) to be good
# *** Only use this function if you are absolutely sure of what you need!
def ref_array_onerow(filelist, formatpars, iy, ny, tslices, verbose):
  num_files = len(filelist)
  ntslice_use = len(tslices)
  output_array = numpy.zeros((num_files, ny, 2*ntslice_use+1))
  dy = get_nside(formatpars)//ny
  for ifile in range(num_files):
    ymin = dy*iy
    ymax = ymin+dy
    output_array[ifile, iy, :] = numpy.asarray(ref_corr(filelist[ifile], formatpars, [ymin,ymax], tslices, False))
    if verbose:
      print ifile, iy
      print output_array[ifile, iy, :]
  return(output_array)
#
# similar but uses a user-specified range of y-values, and output lacks the 'iy' index
# (i.e. is 2D array)
def ref_array_block(filelist, formatpars, yrange, tslices, verbose):

  num_files = len(filelist)
  ntslice_use = len(tslices)
  output_array = numpy.zeros((num_files, 2*ntslice_use+1))

  if len(yrange)<2:
    print 'Error in ref_array_block: yrange =', yrange
    exit()
  for ifile in range(num_files):
    ymin = yrange[0]
    ymax = yrange[1]
    output_array[ifile, :] = numpy.asarray(ref_corr(filelist[ifile], formatpars, [ymin,ymax], tslices, False))
    if verbose:
      print ifile
      print output_array[ifile, :]

  return(output_array)

# Generate a 4D date cube containing information on a region of the detector
#
# filename = name of the source FITS file
# formatpars = integer describing which type of format to use
#     format 1: H4RG, all data in a single HDU, ramp slope positive (ex. DCL H4RG-18237 data)
# xyrange = list [xmin,xmax,ymin,ymax] (first row/col are zero) -- EXcluding xmax and ymax!
# tslices = list of time slices to use (first is *1*)
# maskinfo = information on how the masking works (list format, if not enough elements goes to default)
#   maskinfo[0] = range around median to accept (default: 0.1, must be within 10% of median)
#   maskinfo[1] = boolean, mask assuming light exposure (default: True)
#
# verbose = True or False (use True only for de-bugging)
#
# Returns a 4D array of dimension number of files +1, number tslices, ymax-ymin, xmax-xmin
#   the *last* "file" is the mask (0 or 1)
#
def pixel_data(filelist, formatpars, xyrange, tslices, maskinfo, verbose):

  # Masking parameters
  cut_offset = 0.1
  if len(maskinfo)>=1: cut_offset = maskinfo[0]
  do_mask = True
  if len(maskinfo)>=2: do_mask = maskinfo[1]

  num_files = len(filelist)
  ntslice_use = len(tslices)
  output_array = numpy.zeros((num_files+1, ntslice_use, xyrange[3]-xyrange[2], xyrange[1]-xyrange[0]))

  for ifile in range(num_files):
    output_array[ifile,:,:,:] = load_segment(filelist[ifile], formatpars, xyrange, tslices, verbose)

  # Generate mean CDS image and consider the median
  mCDS = numpy.mean(output_array[0:num_files,0,:,:], axis=0) - numpy.mean(output_array[0:num_files,-1,:,:], axis=0)
  mCDS_med = numpy.median(mCDS)
  if do_mask:
    a = (1./mCDS_med)*mCDS
    goodmap = numpy.where(numpy.logical_and(a>1-cut_offset,a<1+cut_offset),1,0)
  else:
    goodmap = numpy.ones_like(mCDS)
  for f in range(num_files):
    for t in range(ntslice_use):
      goodmap *= numpy.where(output_array[f,t,:,:]>0,1,0)
  if verbose:
    print 'Median =', mCDS_med, 'cut_offset =', cut_offset
    print goodmap
    print goodmap.shape
  # Copy map of good pixels into the output
  for t in range(ntslice_use):
    output_array[num_files,t,:,:] = goodmap

  return output_array

# Routine to get IPC-corrected gain
# 
# Inputs:
#   graw      = uncorrected gain (e/DN)
#   CH        = horizontal correlation (DN^2)
#   CV        = vertical correlation (DN^2)
#   signal    = signal in this ramp (DN)
#
# Output list:
#   gain (alpha corr), e/DN
#   alphaH
#   alphaV
#
# returns [] if failed.
def gain_alphacorr(graw, CH, CV, signal):
  g = graw
  for i in range(100):
    alphaH = CH*g/(2*signal)
    alphaV = CV*g/(2*signal)
    if (alphaH+alphaV>0.25): return [] # FAIL!
    g = graw*( (1-2*(alphaH+alphaV))**2 + 2*(alphaH**2+alphaV**2) )
  return [g, alphaH, alphaV]

# Routine to get IPC+NL-corrected gain
#
# Inputs:
#   graw        = uncorrected gain (e/DN)
#   CH          = horizontal correlation (DN^2)
#   CV          = vertical correlation (DN^2)
#   signal      = signal in this ramp (DN)
#   frac_dslope = mean signal rate in (cd) / mean signal rate in (ab) - 1
#   times       = list of times [a,b,c,d] used, normalized to reference slice
#
# Output list:
#   gain g (alpha corr), e/DN
#   alphaH
#   alphaV
#   beta
#   current I (electrons per time slice)
#
# returns [] if failed
def gain_alphabetacorr(graw, CH, CV, signal, frac_dslope, times):

  # This is solving the following set of equations
  # (see Hirata's brighter-fatter effect paper)
  #
  # graw = g * [ 1 + beta I (3tb+3td-4ta) ] / [ (1-4alpha)^2 + 2alphaH^2 + 2alphaV^2 ]
  # CH = (2 I tad alphaH / g^2) [ 1 - 4alpha - 4 beta I td ]
  # CV = (2 I tad alphaV / g^2) [ 1 - 4alpha - 4 beta I td ]
  # signal = I tad [ 1 - beta I (ta+td) ] / g
  # frac_dslope = - beta I (tc+td-ta-tb)

  # Initial guess
  g = graw
  alpha = alphaH = alphaV = beta = 0
  I = signal*g

  # Iterate
  # (100 iterations is overkill for this problem if alpha and beta are small)
  for numIter in range(100):
    g = graw * ((1-4*alpha)**2+2*(alphaH**2+alphaV**2)) / (1+beta*I*(3*(times[1]+times[3])-4*times[0]))
    if g<1e-3:
      print 'Gain did not converge'
      print 'IN:', graw, CH, CV, signal, frac_dslope, times
      print 'STATUS:', g, alphaH, alphaV, alpha, I, beta
      exit()
    temp = (1-4*alpha-4*beta*I*times[3])*2*I*(times[3]-times[0])/g**2
    alphaH = CH/temp
    alphaV = CV/temp
    if (alphaH+alphaV>0.25): return [] # FAIL!
    alpha = (alphaH+alphaV)/2.
    I = signal*g/(times[3]-times[0])/(1-beta*I*(times[3]+times[0]))
    beta = -frac_dslope/I/(times[2]+times[3]-times[0]-times[1])
    if numpy.fabs(beta)*I*(times[3]+times[0])>0.5: return [] # FAIL!

  return [g, alphaH, alphaV, beta, I]

# Basic characterization of a data cube
#
# region_cube = 4D array of the region of interest (order of indices: file, timeslice, y-ymin, x-xmin)
# dark_cube = same, but for a suite of darks
# tslices = list of time slices
# lightref = reference pixel table for correcting light exposures (2D)
#   size is num_files, 2*ntslice_use+1 (assumes we are taking the correct y-slice)
# darkref = same as for lightref
# ctrl_pars = control parameter list
#   ctrl_pars[0] = cut fraction (default to 0.01)
#   ctrl_pars[1] = mean subtraction for the IPC correlation? (default to True)
#   ctrl_pars[2] = noise subtraction for the IPC correlation? (default to True)
#   ctrl_pars[3] = reset frame (default to 0)
#   ctrl_pars[4] = reference pixel subtraction? (default to True)
#   ctrl_pars[5] = which parameters to report (default to True = standard basic pars; False = correlation data instead)
# verbose = True or False  (recommend True only for de-bugging)
#
# Returns a list of basic calibration parameters.
# if ctrl_pars[5] is True
#   [number of good pixels, gain_raw, gain_acorr, gain_abcorr, aH, aV, beta, I, tCH, tCV]
# if False:
#   [number of good pixels, median, variance, tCH, tCV]
# Returns the null list [] if failed.
#
# Includes a test so this won't crash if tslices[1]>=tslices[-1] but returns meaningful x-correlation C_{abab}
# (everything else is nonsense in this case)
#
def basic(region_cube, dark_cube, tslices, lightref, darkref, ctrl_pars, verbose):

  # Settings:
  newMeanSubMethod = True     # use False only for test/debug

  # Extract basic parameters
  num_files = region_cube.shape[0]-1
  nt = region_cube.shape[1]
  dy = region_cube.shape[2]
  dx = region_cube.shape[3]
  npix = dx*dy
  if nt!=len(tslices):
    print 'Error in pyirc.basic: incompatible number of time slices'
    exit()
  if verbose: print 'nfiles = ',num_files,', ntimes = ',nt,', dx,dy=',dx,dy
  treset = 0
  if len(ctrl_pars)>=4: treset = ctrl_pars[3]

  # First get correlation parameters
  epsilon = .01
  if len(ctrl_pars)>=1: epsilon = ctrl_pars[0]
  subtr_corr = True
  if len(ctrl_pars)>=2: subtr_corr = ctrl_pars[1]
  noise_corr = True
  if len(ctrl_pars)>=3: noise_corr = ctrl_pars[2]
  if verbose: print 'corr pars =', epsilon, subtr_corr, noise_corr
  #

  # Reference pixel subtraction?
  subtr_href = True
  if len(ctrl_pars)>=5: subtr_href = ctrl_pars[4]

  # return full correlation information?
  full_corr = True
  if len(ctrl_pars)>=6: full_corr = ctrl_pars[5]

  # Get means and variances at the early and last slices
  # (i.e. 1-point information)
  gauss_iqr_in_sigmas = scipy.stats.norm.ppf(.75)*2  # about 1.349
  box1 = region_cube[0:num_files,0,:,:] - region_cube[0:num_files,1,:,:]
  box2 = region_cube[0:num_files,0,:,:] - region_cube[0:num_files,-1,:,:]
  box2Noise = dark_cube[0:num_files,0,:,:] - dark_cube[0:num_files,-1,:,:]
  #
  if subtr_href:
    for f in range(num_files):
      if verbose: print 'lightref.shape=',lightref.shape, 'subtr ->', lightref[f,nt+1], lightref[f,2*nt-1], darkref[f,2*nt-1]
      box1[f,:,:] -= lightref[f,nt+1]
      box2[f,:,:] -= lightref[f,2*nt-1]
      box2Noise[f,:,:] -= darkref[f,2*nt-1]
  mean1 = numpy.mean(box1, axis=0)
  mean2 = numpy.mean(box2, axis=0)
  med1 = numpy.median(mean1)
  med2 = numpy.median(mean2)
  var1 = 0
  var2 = 0
  corr_mask = region_cube[-1,0,:,:]
  for if1 in range(1,num_files):
    for if2 in range(if1):
      temp_box = box1[if1,:,:] - box1[if2,:,:]
      iqr1 = pyIRC_percentile(temp_box,corr_mask,75) - pyIRC_percentile(temp_box,corr_mask,25)
      temp_box = box2[if1,:,:] - box2[if2,:,:]
      iqr2 = pyIRC_percentile(temp_box,corr_mask,75) - pyIRC_percentile(temp_box,corr_mask,25)
      var1 += (iqr1/gauss_iqr_in_sigmas)**2/2.
      var2 += (iqr2/gauss_iqr_in_sigmas)**2/2.
      if verbose: print 'Inner loop,', if1, if2, temp_box.shape
  var1 /= num_files*(num_files-1)/2.
  var2 /= num_files*(num_files-1)/2.
  if var2<=var1 and tslices[1]<tslices[-1]: return [] # FAIL!
  gain_raw = (med2-med1)/(var2-var1+1e-100) # in e/DN
    # 1e-100 does nothing except to prevent an error when var1 and var2 are exactly the same

  # Correlations of neighboring pixels, in DN^2
  #
  tCH = tCV = 0
  for if1 in range(1,num_files):
    for if2 in range(if1):
      temp_box = box2[if1,:,:] - box2[if2,:,:]

      # Run through twice if we have noise, otherwise once
      nrun = 2 if noise_corr else 1
      for icorr in range (nrun):
        # clipping
        cmin = pyIRC_percentile(temp_box,corr_mask,100*epsilon)
        cmax = pyIRC_percentile(temp_box,corr_mask,100*(1-epsilon))
        this_mask = numpy.where(numpy.logical_and(temp_box>cmin,temp_box<cmax),1,0) * corr_mask
        if numpy.sum(this_mask)<1: return [] # FAIL!
        # mean subtraction
        mean_of_temp_box = numpy.sum(temp_box*this_mask)/numpy.sum(this_mask)
        if subtr_corr and newMeanSubMethod: temp_box -= mean_of_temp_box

        # Correlations in horizontal and vertical directions
        maskCV = numpy.sum(this_mask[:-1,:]*this_mask[1:,:])
        maskCH = numpy.sum(this_mask[:,:-1]*this_mask[:,1:])
        CV = numpy.sum(this_mask[:-1,:]*this_mask[1:,:]*temp_box[:-1,:]*temp_box[1:,:])
        CH = numpy.sum(this_mask[:,:-1]*this_mask[:,1:]*temp_box[:,:-1]*temp_box[:,1:])
        if maskCH<1 or maskCV<1: return []
        CH /= maskCH
        CV /= maskCV

        if subtr_corr and not newMeanSubMethod:
          CH -= mean_of_temp_box**2
          CV -= mean_of_temp_box**2
        tCH += CH * (1 if icorr==0 else -1)
        tCV += CV * (1 if icorr==0 else -1)

        if verbose:
          print 'pos =', if1, if2, 'iteration', icorr, 'cmin,cmax =', cmin, cmax
          print 'Mask size', numpy.sum(this_mask), 'correlations =', maskCH, maskCV, 'data:', CH, CV

        temp_box = box2Noise[if1,:,:] - box2Noise[if2,:,:]
        # end nested for loop
  #
  # Normalize covariances. Note that taking the difference of 2 frames doubled the covariance
  # matrix, so we have introduced cov_clip_corr
  xi = scipy.stats.norm.ppf(1-epsilon)
  cov_clip_corr = (1. - numpy.sqrt(2./numpy.pi)*xi*numpy.exp(-xi*xi/2.)/(1.-2.*epsilon) )**2
  tCH /= num_files*(num_files-1)*cov_clip_corr
  tCV /= num_files*(num_files-1)*cov_clip_corr

  # if we don't need full correlations, exit now
  if not full_corr:
    return [numpy.sum(this_mask), med2, var2, tCH, tCV]

  # Curvature information (for 2nd order NL coefficient)
  if (tslices[-1]!=tslices[-2]):
    if subtr_href:
      for f in range(num_files):
        box1[f,:,:] += lightref[f,nt+1]
    boxD = region_cube[0:num_files,-2,:,:] - region_cube[0:num_files,-1,:,:]\
           - (tslices[-1]-tslices[-2])/float(tslices[1]-tslices[0])*box1
           # difference map
    if subtr_href:
      for f in range(num_files):
        box1[f,:,:] -= lightref[f,nt+1]
        boxD[f,:,:] -= (tslices[-1]-tslices[-2])/float(tslices[1]-tslices[0]) * lightref[f,2*nt]
    fac0 = fac1 = 0
    for if1 in range(num_files):
      box1R = box1[if1,:,:]
      boxDR = boxD[if1,:,:]
      c1min = pyIRC_percentile(box1R, corr_mask, 100*epsilon)
      if c1min<=.5: c1min = .5   # should have no effect if successful, but prevents division by 0 if failure
      c1max = pyIRC_percentile(box1R, corr_mask, 100*(1-epsilon))
      cDmin = pyIRC_percentile(boxDR, corr_mask, 100*epsilon)
      cDmax = pyIRC_percentile(boxDR, corr_mask, 100*(1-epsilon))
      this_file_mask = numpy.where(numpy.logical_and(box1R>c1min, numpy.logical_and(box1R<c1max,
        numpy.logical_and(boxDR>cDmin, boxDR<cDmax))), corr_mask, 0)
      fac0 += numpy.sum(this_file_mask*boxDR)
      fac1 += numpy.sum(this_file_mask*box1R)
    if fac1<.5: return [] # FAIL!
    frac_dslope = fac0/fac1/((tslices[-1]-tslices[-2])/float(tslices[1]-tslices[0]))
  else:
    frac_dslope = 0.
  if verbose: print 'frac_dslope =', frac_dslope

  if verbose:
    print 'Group 1 ->', med1, var1
    print 'Group 2 ->', med2, var2
    print 'correlations in Group 2:', tCH, tCV
    print 'factors used: xi =', xi, ', cov_clip_corr =', cov_clip_corr

  # Get alpha-corrected gains
  out = gain_alphacorr(gain_raw, tCH, tCV, med2)
  if tslices[1]>=tslices[-1] and len(out)<1:
    return [numpy.sum(this_mask), gain_raw, gain_raw, gain_raw, 0., 0., 0., med2/gain_raw/(tslices[1]-tslices[0]), tCH, tCV]
  if len(out)<1: return [] # FAIL!
  gain_acorr = out[0]
  aH = out[1]
  aV = out[2]

  if tslices[1]>=tslices[-1]:
    return [numpy.sum(this_mask), gain_raw, gain_acorr, gain_acorr, aH, aV, 0., med2/gain_acorr/(tslices[1]-tslices[0]), tCH, tCV]

  out = gain_alphabetacorr(gain_raw, tCH, tCV, med2, frac_dslope, [t-treset for t in tslices])
  if len(out)<1: return [] # FAIL!
  gain_abcorr = out[0]
  aH = out[1]
  aV = out[2]
  beta = out[3]
  I = out[4]

  return [numpy.sum(this_mask), gain_raw, gain_acorr, gain_abcorr, aH, aV, beta, I, tCH, tCV]

# Routine to obtain statistical properties of a region of the detector across many time slices
#
# Inputs:
# lightfiles = list of light files
# darkfiles = list of dark files
# formatpars = format parameters
# box = list [xmin, xmax, ymin, ymax]
# tslices = list [tmin, tmax, deltas ...] (Python format -- xmax, ymax, tmax not included)
#   if no deltas (tslices length 2) then compute everything; if deltas specified, then only compute
#   correlations at the specified deltas (e.g. [1,3] for delta t = 1 or 3)
# sensitivity_spread_cut = for good pixels (typically 0.1)
# ctrl_pars = parameters for basic
#
# Each data[ti,tj,:] contains:
#   [number of good pixels, median, variance, tCH, tCV]
def corrstats(lightfiles, darkfiles, formatpars, box, tslices, sensitivity_spread_cut, ctrl_pars):

  # make copy of ctrl_pars, but force 5th element to be False
  ctrl_pars2 = ctrl_pars[:]
  if len(ctrl_pars2)<6: ctrl_pars2.append(False)
  ctrl_pars2[5] = False

  tmin = tslices[0]; tmax = tslices[1]; nt = tmax-tmin
  # build cube of good pixels, medians, variances, correlations
  data = numpy.zeros((nt,nt,5))
  # and get mask (last 'time' slice) -- only thing we are extracting from region_cube_X
  region_cube_X = pixel_data(lightfiles, formatpars, box[:4], [tmin,tmax-1,tmax-1,tmax-1], [sensitivity_spread_cut, True], False)

  # Get list of (good pix, median, var, cov_H, cov_V)
  for ti in range(nt-1):
    for tj in range(ti+1,nt):
      if tslices[2:]==[] or tj-ti in tslices[2:] or tj-ti==nt-1:
        t1 = tmin+ti
        t2 = tmin+tj
        tarray = [t1,t2,t2,t2]
        lightref = ref_array_block(lightfiles, formatpars, box[2:4], tarray, False)
        darkref = ref_array_block(darkfiles, formatpars, box[2:4], tarray, False)
        region_cube = pixel_data(lightfiles, formatpars, box[:4], tarray, [sensitivity_spread_cut, False], False)
        dark_cube = pixel_data(darkfiles, formatpars, box[:4], tarray, [sensitivity_spread_cut, False], False)
        # switch to the mask from above
        region_cube[-1,:,:,:] = region_cube_X[-1,:,:,:]
        dark_cube[-1,:,:,:] = region_cube_X[-1,:,:,:]
        B = basic(region_cube, dark_cube, tarray, lightref, darkref, ctrl_pars2, False)
        if len(B)==5: data[ti,tj,:] = numpy.asarray(B)
        # print t1, t2, data[ti,tj,:]

  return data

# Routine to characterize of a region of the detector across many time slices
#
# Inputs:
# lightfiles = list of light files
# darkfiles = list of dark files
# formatpars = format parameters
# box = list [xmin, xmax, ymin, ymax]
# tslices = list [tmin, tmax, dt1, dt2] (Python format -- xmax, ymax, tmax not included)
#   correlations at the specified dt's are used (e.g. [1,5])
# sensitivity_spread_cut = for good pixels (typically 0.1)
# ctrl_pars = parameters for basic
# addInfo = additional information (sometimes needed)
# 
# return value is [isgood (1/0), g, aH, aV, beta, I, da (residual)]
#
def polychar(lightfiles, darkfiles, formatpars, box, tslices, sensitivity_spread_cut, ctrl_pars, addInfo):

  # Check time range
  if len(tslices)<4:
    print 'Error: polychar: not enough data', tslices
    return []
  if tslices[2]>=tslices[3] or tslices[3]>=tslices[1]-tslices[0] or tslices[1]-tslices[0]<3:
    print 'Error: polychar: invalid slices range', tslices
    return []

  # Get correlation function data (including adjacent steps))
  data = corrstats(lightfiles, darkfiles, formatpars, box, tslices+[1], sensitivity_spread_cut, ctrl_pars)

  # check if this is good
  nt = tslices[1]-tslices[0]
  for ti in range(nt-1):
    for tj in range(ti+1,nt):
      if data[ti,tj,0]==0 and tj-ti in [1,tslices[2],tslices[3]]:
        return [0,0,0,0,0,0]

  # Determine whether we are applying corrections
  applyCorr = False
  if len(addInfo)>=2:
    applyCorr = True
    typeCorr = addInfo[0]
    ipnl = addInfo[1]
    sBFE = numpy.shape(ipnl)[0]//2

  # Fit of differences as a function of slice number
  # slope = -2*beta*I^2/g
  # intercept = (I - beta I^2)/g
  npts = tslices[1]-tslices[0]-1
  diff_frames = numpy.zeros((npts))
  for j in range(npts):
    diff_frames[j] = data[j,j+1,1] # median from frame tslices[0]+j -> tslices[0]+j+1
  slopemed, icpt = numpy.linalg.lstsq(numpy.vstack([numpy.array(range(npts)) + tslices[0]-ctrl_pars[3],
                   numpy.ones(npts)]).T, diff_frames)[0]

  # Difference of correlation functions
  #
  # Cdiff = I/g^2 * ((1-4a)^2 + 2aH^2 + 2aV^2) * t_{bd} - 4(1-8a)beta I^2/g^2 * (t_{ad}t_d - t_{ab}t_b + (e-1)/2*t_{bd})
  # where e = npts2 is number of bins averaged together
  #
  # and horizontal and vertical cross-correlations
  # CH = 2 I t_{ab} / g^2 * ( 1-4a - 4 beta (I t_b + 1/2 + (e-1)/2*I) ) * aH
  # CV = 2 I t_{ab} / g^2 * ( 1-4a - 4 beta (I t_b + 1/2 + (e-1)/2*I) ) * aV
  #
  npts2 = tslices[1]-tslices[0]-tslices[3]
  Cdiff = CV = CH = 0.
  for j in range(npts2):
    Cdiff += data[j,j+tslices[3],2] - data[j,j+tslices[2],2]
    CH += data[j,j+tslices[3],3]
    CV += data[j,j+tslices[3],4]
  Cdiff /= npts2; CH /= npts2; CV /= npts2

  # initialize with no IPC or NL
  alphaH = alphaV = alpha = beta = 0.
  da = 1.
  # dummy initializations; these get over-written before they are used
  I = g = 1.
  Cdiffcorr = 0.
  for iCycle in range(100):
    alphaH_old = alphaH; alphaV_old = alphaV # to track convergence

    # Get combination of I and gain from difference of correlation functions
    tbrack = tslices[3]*(tslices[0]+tslices[3]-ctrl_pars[3]) - tslices[2]*(tslices[0]+tslices[2]-ctrl_pars[3])\
             + (npts2-1)/2.0*(tslices[3]-tslices[2])
    I__g2 = (Cdiff - Cdiffcorr + 4.*(1.-8.*alpha)*beta*I**2/g**2*tbrack) / (tslices[3]-tslices[2]) / ( (1.-4*alpha)**2 + 2*alphaH**2+2*alphaV**2 )

    # Now use slopemed = -2 beta I^2/g, icpt = (I - beta I^2)/g, and I/g^2 to solve for I, beta, and g
    g = (icpt - slopemed/2.)/I__g2
    I = I__g2 * g**2
    beta = -g*slopemed/2./I**2

    # Corrections to horiz. and vert. IPC
    #
    CHcorr = CVcorr = 0.
    if applyCorr:
      if typeCorr.lower() == 'bfe':
        CHcorr = (ipnl[sBFE,sBFE+1]+ipnl[sBFE,sBFE-1])/2. * (I/g*tslices[3])**2
        CVcorr = (ipnl[sBFE+1,sBFE]+ipnl[sBFE-1,sBFE])/2. * (I/g*tslices[3])**2
        Cdiffcorr = ipnl[sBFE,sBFE] * (I/g)**2*(tslices[3]**2-tslices[2]**2)

    factor = 2.*I__g2*tslices[3] * ( 1.-4.*alpha - 4.*beta*( I*(tslices[0]+tslices[3]-ctrl_pars[3]+(npts2-1.)/2.) +0.5) )
    alphaH = (CH - CHcorr)/factor
    alphaV = (CV - CVcorr)/factor
    alpha = (alphaH+alphaV)/2.
    da = numpy.abs(alphaH_old-alphaH) + numpy.abs(alphaV_old-alphaV)

  return [1, g, alphaH, alphaV, beta, I, da]

# Routines to compute the BFE coefficients
#
# Inputs:
# region_cube = 4D array of the region of interest (order of indices: file, timeslice, y-ymin, x-xmin)
# tslices = list of time slices
# basicinfo = output from basic (incl. gains, IPC, NL)
# ctrl_pars_bfe = parameters to control BFE determination
#   ctrl_pars_bfe[0] = cut fraction (default to 0.01)
#   ctrl_pars_bfe[1] = reset frame (default to 0)
#   ctrl_pars_bfe[2] = max range for BFE kernel estimation (default to 2)
#   ctrl_pars_bfe[3] = baseline subtraction? (default to True)
# verbose = True or False (recommend True only for debugging)
#
# output is a fsBFE x fsBFE (default: 5x5) BFE kernel in inverse electrons
#
def bfe(region_cube, tslices, basicinfo, ctrl_pars_bfe, verbose):

  # Extract parameters from basicinfo
  gain =   basicinfo[3]
  aH =     basicinfo[4]
  aV =     basicinfo[5]
  beta =   basicinfo[6]
  I =      basicinfo[7]

  # Extract basic parameters
  num_files = region_cube.shape[0]-1
  nt = region_cube.shape[1]
  dy = region_cube.shape[2]
  dx = region_cube.shape[3]
  npix = dx*dy
  if (nt!=len(tslices)):
    print 'Error in basic: incompatible number of time slices'
    exit()
  if verbose: print 'nfiles = ',num_files,', ntimes = ',nt,', dx,dy=',dx,dy
  treset = 0
  if len(ctrl_pars_bfe)>=2: treset = ctrl_pars_bfe[1]

  # BFE kernel size:
  # sBFE = range; fsBFE = full size
  sBFE = 2
  if len(ctrl_pars_bfe)>=3: sBFE = ctrl_pars_bfe[2]
  fsBFE = 2*sBFE+1
  sBFE_out = sBFE
  fsBFE_out = fsBFE

  # Baseline subtraction -- requires bigger box
  BSub = True
  if len(ctrl_pars_bfe)>=4: BSub = ctrl_pars_bfe[3]
  if BSub:
    sBFE = max(sBFE_out, 10)
    fsBFE = 2*sBFE+1
    pad = 5 # Number of pixels in corr. fcn. to take for the baseline on each side in each row

  # Cut fraction and correction
  epsilon = .01
  if len(ctrl_pars_bfe)>=1: epsilon = ctrl_pars_bfe[0]
  xi = scipy.stats.norm.ppf(1-epsilon)
  cov_clip_corr = (1. - numpy.sqrt(2./numpy.pi)*xi*numpy.exp(-xi*xi/2.)/(1.-2.*epsilon) )**2

  # Build the two slices to correlate
  box1 = region_cube[0:num_files,0,:,:] - region_cube[0:num_files,1,:,:]
  box3 = region_cube[0:num_files,-2,:,:] - region_cube[0:num_files,-1,:,:]
  corr_mask = region_cube[-1,0,:,:]

  # setup for BFE kernel
  numBFE = numpy.zeros((fsBFE,fsBFE))
  denBFE = numpy.zeros((fsBFE,fsBFE))

  # Loop over the flat pairs we are going to use
  for if1 in range(1,num_files):
    for if2 in range(if1):
      # Build slices and mask
      slice_ab = box1[if1,:,:] - box1[if2,:,:]
      slice_cd = box3[if1,:,:] - box3[if2,:,:]
      ab_min = pyIRC_percentile(slice_ab, corr_mask, 100*epsilon)
      ab_max = pyIRC_percentile(slice_ab, corr_mask, 100*(1-epsilon))
      cd_min = pyIRC_percentile(slice_cd, corr_mask, 100*epsilon)
      cd_max = pyIRC_percentile(slice_cd, corr_mask, 100*(1-epsilon))
      this_file_mask = numpy.where(numpy.logical_and(slice_ab>ab_min, numpy.logical_and(slice_ab<ab_max,
        numpy.logical_and(slice_cd>cd_min, slice_cd<cd_max))), corr_mask, 0)
      if verbose:
        print if1, if2, slice_ab.shape, slice_cd.shape, this_file_mask.shape, numpy.sum(this_file_mask)

      # Mean subtraction
      slice_ab -= pyIRC_mean(slice_ab, this_file_mask)
      slice_cd -= pyIRC_mean(slice_cd, this_file_mask)
      # Set masked values to zero
      slice_ab *= this_file_mask
      slice_cd *= this_file_mask

      # Now get the correlation function ...
      # format is: numerator and denominator of C_{abcd}(2*sBFE-i,2*sBFE-j)
      for j in range(fsBFE):
        for i in range(fsBFE):
          abminX = 0
          abmaxX = dx
          abminY = 0
          abmaxY = dy
          if i>=sBFE:
            abmaxX += sBFE-i
          else:
            abminX += sBFE-i
          if j>=sBFE:
            abmaxY += sBFE-j
          else:
            abminY += sBFE-j
          cdminX = abminX + i - sBFE
          cdmaxX = abmaxX + i - sBFE
          cdminY = abminY + j - sBFE
          cdmaxY = abmaxY + j - sBFE

          # Add up contributions to the correlation function
          denBFE[j,i] += numpy.sum(this_file_mask[abminY:abmaxY,abminX:abmaxX]*this_file_mask[cdminY:cdmaxY,cdminX:cdmaxX])
          numBFE[j,i] += numpy.sum(slice_ab[abminY:abmaxY,abminX:abmaxX]*slice_cd[cdminY:cdmaxY,cdminX:cdmaxX])/2.
          # division by 2 since differencing two images doubles the answer

  BFEK = numBFE/(denBFE+1e-99)
  BFEK *= gain**2/(I**2*(tslices[1]-tslices[0])*(tslices[-1]-tslices[-2])*cov_clip_corr)

  # Baseline subtraction
  if BSub:
    for j in range(fsBFE):
      rowBL = ( numpy.mean(BFEK[j,0:pad]) + numpy.mean(BFEK[j,-pad:]) )/2.
      BFEK[j,:] -= rowBL

  # Corrections for classical non-linearity
  BFEK[sBFE,sBFE] += 2*(1-4*(aH+aV))*beta
  if sBFE>=1:
    BFEK[sBFE,sBFE+1] += 4*aH*beta
    BFEK[sBFE,sBFE-1] += 4*aH*beta
    BFEK[sBFE+1,sBFE] += 4*aV*beta
    BFEK[sBFE-1,sBFE] += 4*aV*beta
  return BFEK[sBFE-sBFE_out:sBFE+sBFE_out+1, sBFE-sBFE_out:sBFE+sBFE_out+1]

# Hot pixel identification
# Returns a tuple of hot pixels in the array that meet the following criteria:
# (*) apparent brightness in time slices up through tslices[-1] is assessed
# (*) in range from pars[0] .. pars[1] in last slice
# (*) repeatable to within a top-to-bottom error of pars[2] as a fraction of the
#       maximum signal (e.g. 0.1 for 10% repeatability)
# (*) isolation: if pars[3]>0, rejects pixels with neighbors that are at least pars[3] times
#       as bright as this pixel itself (e.g. 0.1 for 10% isolation)
#
def hotpix(darkfiles, formatpars, tslices, pars, verbose):

  # Build array for the dark cube
  ndarks = len(darkfiles)
  N = get_nside(formatpars)
  cube = numpy.zeros((ndarks,N,N))
  for f in range(ndarks):
    CDS = load_segment(darkfiles[f], formatpars, [0,N,0,N], [1,tslices[-1]], False)
    cube[f,:,:] = CDS[0,:,:] - CDS[1,:,:]

  # Extract information on the pixels
  this_hot = numpy.zeros((N,N))
  ave_cube = numpy.mean(cube, axis=0)
  d_cube = numpy.max(cube, axis=0) - numpy.min(cube, axis=0)
  if verbose:
    print 'time slices for hot pixel analysis ->', tslices
    print ave_cube
    print '->', ave_cube.shape
    print d_cube
    print '->', d_cube.shape

  this_hot = numpy.where(numpy.logical_and(ave_cube>=pars[0], ave_cube<=pars[1]), 1, 0)

  # Isolation cut
  if verbose: print 'Start with', numpy.sum(this_hot), 'pixels before isolation cut'
  if pars[3]>0:
    C = 2
    M = numpy.ones((2*C+1,2*C+1))
    M[C,C]=0
    isolation_mask = scipy.ndimage.maximum_filter(ave_cube, footprint=M, mode='constant', cval=0)
    # Also avoid pixels that border on reference pixels
    this_hot[:4+C,:] = 0
    this_hot[-(4+C):,:] = 0
    this_hot[:,:4+C] = 0
    this_hot[:,-(4+C):] = 0
    this_hot *= numpy.where(isolation_mask<=pars[3]*ave_cube, 1, 0)

  if verbose: print 'Start with', numpy.sum(this_hot), 'pixels'
  for t in tslices[1:]:
    for f in range(ndarks):
      CDS = load_segment(darkfiles[f], formatpars, [0,N,0,N], [1,t], False)
      cube[f,:,:] = CDS[0,:,:] - CDS[1,:,:]
    d_cube = numpy.max(cube, axis=0) - numpy.min(cube, axis=0)
    this_hot *= numpy.where(d_cube<=pars[2]*ave_cube, 1, 0)
  if verbose: print numpy.sum(this_hot)

  return numpy.where(this_hot>0)

# Generates min and max range for a color bar
# based on inter-quartile range
def get_vmin_vmax(mydata, qext):
  Q1 = numpy.nanpercentile(mydata,25)
  Q2 = numpy.nanpercentile(mydata,75)
  return Q1-(Q2-Q1)*qext, Q2+(Q2-Q1)*qext
