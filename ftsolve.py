import numpy as np
from numpy.fft import fft2,ifft2
import warnings
import pdb

def center(arr):
    # Transforms kernel so that it looks as expected to the eye:
    # Returns version of kernel with (0,0) in center, y=-1 down, x=-1 left, etc.
    # Centered arrays should *NOT* be used for calculations! For human reference only :)
    size = (len(arr)+1)//2
    return np.rot90(np.roll(np.roll(arr,-size,axis=1),-size,axis=0),-1,axes=(1,0))

def decenter(arr):
    # Transforms kernel from human-readable to numpy-readable 
    # Only decentered arrays should be used for calculations
    size = (len(arr)+1)//2
    return np.roll(np.roll(np.rot90(arr,axes=(1,0)),size,axis=0),size,axis=1)

def pad_to_N(arr,N):
    # pads array out to size NxN (if arr is smaller than this)
    # input assumed to be decentered
    if not arr.shape[0]>N:
        pad_size = (N-arr.shape[0])//2
        return decenter(np.pad(center(arr),pad_size,mode='constant'))
    else:
        return arr

def solve_corr(bfek,N,I,g,beta,sigma_a,tslices,avals,avals_nl=[0,0,0]):
    # INPUT: 
    # bfek     <- compound kernel [K^2 a+KK*](assumed to be decentered)
    # N        <- detector size (assumed odd for now)
    # I        <- current
    # g        <- gain (assuming no higher order fitting for now)
    # beta     <- classical non-linearity
    # sigma_a  <- sum of the BFE kernel
    # tslices  <- list of time slices (ta, tb, tc, td)  
    # avals    <- list of alpha values for linear IPC kernel (aV, aH, aD)
    # avals_nl <- list of alpha values for NL-IPC kernel (aV_nl, aH_nl, aD_nl)
    # 
    # OUTPUT: C_abcd
    
    ta, tb, tc, td = tslices
    aV, aH, aD = avals
    aV_nl, aH_nl, aD_nl = avals_nl
    
    if not bfek.shape[1]==bfek.shape[0]:
        warnings.warn("WARNING: convolved BFE kernel (BFEK) not square.")
    
    # Calculate K and K* from given alphas
    k = decenter(np.array([[aD,aV,aD],
                           [aH,1-4*aD-2*aV-2*aH,aH],
                           [aD,aV,aD]]))
    
    knl = decenter(np.array([[aD_nl,aV_nl,aD_nl],
                             [aH_nl,1-4*aD_nl-2*aV_nl-2*aH_nl,aH_nl],
                             [aD_nl,aV_nl,aD_nl]]))
    
    # solve Fourier version for asq: F(BFEK) = Ksq^2*asq + Ksq*Knl_sq
    ksq = fft2(pad_to_N(k,N))
    knl_sq = fft2(pad_to_N(knl,N))
    asq = (fft2(pad_to_N(bfek,N)) - ksq*knl_sq)/ksq**2
    a = ifft2(asq)
    a_flipped = decenter(np.flip(center(a).flatten()).reshape(a.shape))
    
    afsq = fft2(a_flipped)
    
    afsq_p = decenter(np.flip(center(afsq).flatten()).reshape(afsq.shape))
    ksq_p = decenter(np.flip(center(ksq).flatten()).reshape(ksq.shape))
    knl_sq_p = decenter(np.flip(center(knl_sq).flatten()).reshape(knl_sq.shape))

    # Calculate Cov(qsq(t),qsq(t')) (see eqn 38)
    qqs = []
    
    for ts in [(ta,tc),(ta,td),(tb,tc),(tb,td)]:
        t1 = min(ts)
        t = max(ts)
        
        qq = (1/(afsq+afsq_p+sigma_a) * np.exp(I*afsq*(t-t1)) *
                                         (np.exp(I*(afsq+afsq_p)*t1)-np.exp(I*sigma_a*t1)))
        qqs.append(qq)
        
    
    # Plug into correlation function (see eqn 51)
    csq_abcd =(1/g**2
               *((1-2*beta*I*ta)*(1-2*beta*I*tc)*(ksq+knl_sq*I*ta)*(ksq_p+knl_sq_p*I*tc)*qqs[0] 
               - (1-2*beta*I*ta)*(1-2*beta*I*td)*(ksq+knl_sq*I*ta)*(ksq_p+knl_sq_p*I*td)*qqs[1] 
               - (1-2*beta*I*tb)*(1-2*beta*I*tc)*(ksq+knl_sq*I*tb)*(ksq_p+knl_sq_p*I*tc)*qqs[2] 
               + (1-2*beta*I*tb)*(1-2*beta*I*td)*(ksq+knl_sq*I*tb)*(ksq_p+knl_sq_p*I*td)*qqs[3])
               )
    
    return np.real(ifft2(csq_abcd))
    
if __name__=="__main__":
   test_bfek = np.load('test_bfek.npy')
   
   N = 21
   I = 1.37
   g = 2.26
   beta = 5.98e-7
   sigma_a = 1.0
   tslices = [3, 11, 13, 21]
   avals = [0.014,0.023,0]
   avals_nl = [0,0,0]

   c_abcd = solve_corr(test_bfek,N,I,g,beta,sigma_a,tslices,avals,avals_nl)
   print c_abcd
   
   
   