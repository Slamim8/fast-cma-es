# Copyright (c) Mingcheng Zuo, Dietmar Wolz.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory.

"""Eigen based implementation of differential evolution (GCL-DE) derived from
    "A case learning-based differential evolution algorithm for global optimization of interplanetary trajectory design,
    Mingcheng Zuo, Guangming Dai, Lei Peng, Maocai Wang, Zhengquan Liu", https://doi.org/10.1016/j.asoc.2020.106451
"""

import sys
import os
import math
import ctypes as ct
import numpy as np
import multiprocessing as mp
from numpy.random import MT19937, Generator
from scipy.optimize import OptimizeResult
from fcmaes.ldecpp import callback_par, call_back_par
from fcmaes.decpp import libcmalib
from fcmaes import de
from fcmaes.evaluator import Evaluator, eval_parallel

os.environ['MKL_DEBUG_CPU_TYPE'] = '5'

def minimize(fun, 
             dim = None,
             bounds = None, 
             popsize = None, 
             max_evaluations = 100000, 
             stop_fitness = None, 
             pbest = 0.7,
             f0 = 0.0,
             cr0 = 0.0,
             rg = Generator(MT19937()),
             runid=0,
             workers = None):  
     
    """Minimization of a scalar function of one or more variables using a 
    C++ GCL Differential Evolution implementation called via ctypes.
     
    Parameters
    ----------
    fun : callable
        The objective function to be minimized.
            ``fun(x, *args) -> float``
        where ``x`` is an 1-D array with shape (dim,) and ``args``
        is a tuple of the fixed parameters needed to completely
        specify the function.
    dim : int
        dimension of the argument of the objective function
    bounds : sequence or `Bounds`
        Bounds on variables. There are two ways to specify the bounds:
            1. Instance of the `scipy.Bounds` class.
            2. Sequence of ``(min, max)`` pairs for each element in `x`.
    popsize : int, optional
        Population size.
    max_evaluations : int, optional
        Forced termination after ``max_evaluations`` function evaluations.
    stop_fitness : float, optional 
         Limit for fitness value. If reached minimize terminates.
    pbest = float, optional
        use low value 0 < pbest <= 1 to narrow search.
    f0 = float, optional
        The initial mutation constant. In the literature this is also known as differential weight, 
        being denoted by F. Should be in the range [0, 2].
    cr0 = float, optional
        The initial recombination constant. Should be in the range [0, 1]. 
        In the literature this is also known as the crossover probability.     
    rg = numpy.random.Generator, optional
        Random generator for creating random guesses.
    runid : int, optional
        id used to identify the run for debugging / logging. 
    workers : int or None, optional
        If not workers is None, function evaluation is performed in parallel for the whole population. 
        Useful for costly objective functions but is deactivated for parallel retry.      
 
           
    Returns
    -------
    res : scipy.OptimizeResult
        The optimization result is represented as an ``OptimizeResult`` object.
        Important attributes are: ``x`` the solution array, 
        ``fun`` the best function value, 
        ``nfev`` the number of function evaluations,
        ``nit`` the number of iterations,
        ``success`` a Boolean flag indicating if the optimizer exited successfully. """
                
    dim, lower, upper = de._check_bounds(bounds, dim)
    if popsize is None:
        popsize = int(dim*8.5+150)
    if lower is None:
        lower = [0]*dim
        upper = [0]*dim
    if stop_fitness is None:
        stop_fitness = math.inf   
    parfun = None if workers is None else parallel(fun, workers)
    array_type = ct.c_double * dim   
    c_callback_par = call_back_par(callback_par(fun, parfun))
    seed = int(rg.uniform(0, 2**32 - 1))
    res = np.empty(dim+4)
    res_p = res.ctypes.data_as(ct.POINTER(ct.c_double))
    try:
        optimizeGCLDE_C(runid, c_callback_par, dim, seed,
                           array_type(*lower), array_type(*upper), 
                           max_evaluations, pbest, stop_fitness,  
                           popsize, f0, cr0, res_p)
        x = res[:dim]
        val = res[dim]
        evals = int(res[dim+1])
        iterations = int(res[dim+2])
        stop = int(res[dim+3])
        if not parfun is None:
            parfun.stop() # stop all parallel evaluation processes
        return OptimizeResult(x=x, fun=val, nfev=evals, nit=iterations, status=stop, success=True)
    except Exception as ex:
        if not workers is None:
            fun.stop() # stop all parallel evaluation processes
        return OptimizeResult(x=None, fun=sys.float_info.max, nfev=0, nit=0, status=-1, success=False)  

class parallel(object):
    """Convert an objective function for parallel execution for cmaes.minimize.
    
    Parameters
    ----------
    fun : objective function mapping a list of float arguments to a float value.
   
    represents a function mapping a list of lists of float arguments to a list of float values
    by applying the input function using parallel processes. stop needs to be called to avoid
    a resource leak"""
        
    def __init__(self, fun, workers = mp.cpu_count()):
        self.evaluator = Evaluator(fun)
        self.evaluator.start(workers)
    
    def __call__(self, xs):
        return eval_parallel(xs, self.evaluator)

    def stop(self):
        self.evaluator.stop()
      
optimizeGCLDE_C = libcmalib.optimizeGCLDE_C
optimizeGCLDE_C.argtypes = [ct.c_long, call_back_par, ct.c_int, ct.c_int, \
            ct.POINTER(ct.c_double), ct.POINTER(ct.c_double), \
            ct.c_int, ct.c_double, ct.c_double, ct.c_int, \
            ct.c_double, ct.c_double, ct.POINTER(ct.c_double)]
         

