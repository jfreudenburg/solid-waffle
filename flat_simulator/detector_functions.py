""" Functions to create various detector effect.
The structure will change, but for now this will be the location for 
functions related to IPC, BFE, etc.
"""
import sys
import numpy as np
from numpy.random import randn,poisson
sys.path.insert(0, '../')
#sys.path.insert(0, '/users/PCON0003/cond0080/src/solid-waffle/')
from pyirc import *
import scipy.signal as signal

def simple_ipc_kernel(alpha=0.01):
  """ Simple function to return a 3 x 3 kernel with an alpha where alpha
  is the kernel value for the 4 adjacent pixels, and the central value is
  1-4*alpha.  This is a symmetric kernel.
  alpha typically on a percent level.
  """
  kernel = np.zeros((3, 3))
  kernel[1,0] = kernel[0,1] = kernel[1,2] = kernel[2,1] = alpha
  kernel[1,1] = 1-4*alpha
  return kernel

def ipc_kernel_HV(alpha_H=0.01,alpha_V=0.01):
  """ Return a 3x3 kernel with horizontal and vertical alpha, which can
  be different.
  """
  kernel = np.zeros((3, 3))
  kernel[0,1] = kernel[2,1] = alpha_H
  kernel[1,0] = kernel[1,2] = alpha_V
  kernel[1,1] = 1-2*alpha_H-2*alpha_V
  return kernel

def calculate_ipc(data_cube_Q, ipc_list, npad=2):
  """ Convolves the input charge data cube with an IPC kernel 
  and returns an output data cube
  Calls 'simple' or 'HV' IPC kernel depending on user input ipc_list
  which is either one value (all directions) or two (horiz, vertical)
  Currently cannot specify horiz or vertically asymmetric alpha
  """
  if len(ipc_list)==1:
    ipc_kern = simple_ipc_kernel(ipc_list[0])
  elif len(ipc_list)==2:
    ipc_kern = ipc_kernel_HV(ipc_list[0], ipc_list[1])
  else:
    raise Exception('Incorrect format of IPC alpha entered')

  # The time samples are given by the first dim of the cube
  for tdx in range(data_cube_Q.shape[0]):
    Q_pad = np.pad(
      data_cube_Q[tdx,:,:], pad_width=(npad,npad), 
      mode='symmetric')
    Q_pad_ipc = signal.convolve(Q_pad, ipc_kern)
    # Dimensions/side for Q_pad_ipc are now 
    # data_cube_Q.shape[0]+ipc_kern.shape[0]+npad-1
    extra_dim = (2*npad+ipc_kern.shape[0]-1)/2
    data_cube_Q[tdx,:,:] = Q_pad_ipc[extra_dim:-extra_dim,
                                     extra_dim:-extra_dim]
  return data_cube_Q


def get_bfe_kernel_3x3():
  """ This returns a simple, currently arbitrary bfe 3 x 3 kernel
  units of 10^-6 per electron
  """
  bfe_kernel_3x3 = 1.E-6*np.array(
    [[0.065, 0.23, 0.065],[0.24, -1.2, 0.24], [0.065, 0.23, 0.065]]) 
  # Currently symmetrical but can put in something more complex
  return bfe_kernel_3x3

def get_bfe_kernel_5x5():
  """ Returns an arbitrary bfe 5x5 kernel
  units of 10&-6 per electron
  """
  bfe_kernel_5x5 = 1.E-6*np.array(
    [[-0.01, 0.0020, -0.0210, -0.019, 0.028],
     [0.0040, 0.0490, 0.2480, 0.01, -0.0240],
     [-0.0170, 0.2990, -1.372, 0.2840, 0.0150],
     [0.0130, 0.0560, 0.2890, 0.0390, 0.02],
     [0.035, 0.0070, 0.0380, 0.0010, 0.026]])
  return np.fliplr(bfe_kernel_5x5)

def calc_area_defect(ap, Q, npad=2):
  """ ap is the a_deltaideltaj coefficient matrix
  Q is the charge going from xmin:xmax and ymin:ymax
  the area defect is unitless
  Q_pad is a padded array with mirror reflection along the
  boundaries
  """
  Q_pad = np.pad(Q, pad_width=(npad,npad), mode='symmetric')
  # Larger-dimensional array must be first arg to convolve
  aQ = signal.convolve(Q_pad, ap) # ap[::-1,::-1])
  W = 1 + aQ
  # Final dimensions of W will be 2*npad+Q.shape[0]+ap.shape[0]-1
  # on each side
  extra_dim = (2*npad+ap.shape[0]-1)/2
  return W[extra_dim:-extra_dim,extra_dim:-extra_dim]

