
import sys
import yaml
import argparse
import numpy as np
import pylab as pl
import corner

from numpy.lib.recfunctions import append_fields

import mcmc, model, plotting, fileio

from ivs.io import ascii
from ivs.units import conversions as cv

default = """
# photometry file with index to the columns containing the photbands, observations and errors
photometryfile: path/to/file.dat
photband_index: 0
obs_index: 1
err_index: 2
# parameters to fit and the limits on them in same order as parameters
pnames: [teff, logg, rad, teff2, logg2, rad2, ebv]
limits:
- [3500, 6000]
- [3.5, 5.0]
- [0.7, 1.5]
- [20000, 40000]
- [4.5, 6.5]
- [0.05, 0.3]
- [0, 0.02]
# constraints on distance and mass ratio if known
constraints:
  q: [3.03, 0.2]
  distance: [600, 50] # in parsec
# added constraints on derived properties as mass, luminosity, luminosity ratio
derived_limits:
  mass: [0.5, 1.0]
  mass2: [0.1, 1.0]
# path to the model grids with integrated photometry
grids: 
- path/to/grid/1.fits
- path/to/grid/2.fits
# setup for the MCMC algorithm
nwalkers: 100    # total number of walkers
nsteps: 2000     # steps taken by each walker (not including burn-in)
nrelax: 500      # burn-in steps taken by each walker
a: 10            # relative size of the steps taken
# output options
datafile: none   # filepath to write results of all walkers
plotpath: none   # filepath to save plots with results
"""

if __name__=="__main__":

   parser = argparse.ArgumentParser()
   parser.add_argument("-f", type=str, dest='filename', default=None,
                       help="use setup given in filename")
   parser.add_argument("-empty", type=str, dest='empty', default=None,
                       help="When used, create an empty setup file with given filename")
   parser.add_argument("-p", action='store_true', dest='plot', 
                       help="Turn on plotting")
   args, variables = parser.parse_known_args()
   
   if not args.empty is None:
      
      ofile = open(args.empty, 'w')
      ofile.write(default)
      ofile.close()
      
      sys.exit()
   
   if args.filename is None:
      
      print "Nothing to do"
      sys.exit()
   
   #-- load the setup file
   setupfile = open(args.filename)
   setup = yaml.safe_load(setupfile)
   setupfile.close()
   
   #-- parse photometry
   data = ascii.read2array(setup['photometryfile'], dtype=str).T
   photbands = data[setup['photband_index']]
   obs = np.array(data[setup['obs_index']], dtype=float)
   obs_err = np.array(data[setup['err_index']], dtype=float) / 2.
   
   #-- pars limits
   pnames = setup['pnames']
   limits = np.array(setup['limits'])
   
   #-- pars constraints
   constraints = setup['constraints']
   if 'distance' in constraints:
      constraints['distance'] = cv.convert('pc', 'Rsol', *constraints['distance'])
   
   #-- pars limits on derived properties
   derived_limits = setup['derived_limits']
   
   #-- pars grid
   gridnames = setup['grids']
   
   grids = []
   for i, name in enumerate(gridnames):
      
      ind = '' if i == 0 else str(i + 1)
      
      axis_values, grid_pars, pixelgrid, grid_names = model.prepare_grid(photbands, name,
            teffrange=limits[pnames.index('teff'+ind)],
            loggrange=limits[pnames.index('logg'+ind)],
            ebvrange =limits[pnames.index('ebv')],
            variables=['teff','logg','ebv'])

      grids.append([axis_values, pixelgrid])
   
   #-- switch logg to g for a binary system
   if 'logg' in pnames:
      limits[pnames.index('logg')] = 10**limits[pnames.index('logg')]
      pnames[pnames.index('logg')] = 'g'
   
   if 'logg2' in pnames:
      limits[pnames.index('logg2')] = 10**limits[pnames.index('logg2')]
      pnames[pnames.index('logg2')] = 'g2'
   
   
   #-- check for variables that are kept fixed
   fixed = np.where(limits[:,0] == limits[:,1])
   varied = np.where(limits[:,0] != limits[:,1])
   
   pnames = np.array(pnames)
   fixed_variables = {}
   for par, val in zip(pnames[fixed], limits[:,0][fixed]):
      fixed_variables[par] = val
      
   pnames = list(pnames[varied])
   limits = limits[varied]
   
   #-- pars mcmc setup
   nwalkers = setup.get('nwalkers', 100)
   nsteps = setup.get('nsteps', 2000)
   nrelax = setup.get('nrelax', 500)
   a = setup.get('a', 10)
   
   
   #-- MCMC
   results, samples = mcmc.MCMC(obs, obs_err, photbands, 
                                 pnames, limits, grids, 
                                 fixed_variables=fixed_variables,
                                 constraints=constraints, derived_limits=derived_limits,
                                 nwalkers=nwalkers, nsteps=nsteps, nrelax=nrelax,
                                 a=a, percentiles=[16, 50, 84])
   
   #-- add fixed variables to results dictionary
   results.update(fixed_variables)
   
   #-- deal with the switch back to logg
   if 'g' in samples.dtype.names:
      samples = append_fields(samples, 'logg', np.log10(samples['g']), usemask=False)
      
   if 'g' in results:
      results['logg'] = np.log10(results['g'])
      
   if 'g2' in samples.dtype.names:
      samples = append_fields(samples, 'logg2', np.log10(samples['g2']), usemask=False)
      
   if 'g2' in results:
      results['logg2'] = np.log10(results['g2'])
      
   
   print "Results:"
   for p, v in results.items():
      print p, v
      
   pc  = np.percentile(samples.view(np.float64).reshape(samples.shape + (-1,)), [50], axis=0)[0]
   print pc
   for p, v in zip(samples.dtype.names, pc):
      print p, v
   
   datafile = setup.get('datafile', None)
   if not datafile is None:
      
      #-- get plain text settings to retain comments and ordering
      setupfile = open(args.filename)
      setup_str = "".join(setupfile.readlines())
      setupfile.close()
      
      fileio.write2fits(samples, datafile, setup=setup_str)
   
   
   plotpath = setup.get('plotpath', None)
   if args.plot or not plotpath is None:
      
      #pars = {}
      #for par, v in zip(samples.dtype.names, results):
         #pars[par] = v[0]
         
      pl.figure(1)
      plotting.plot_fit(obs, obs_err, photbands, pars=results, constraints=constraints)
      if plotpath:
         pl.savefig(plotpath + '/sed_fit.png')
      
      
      if 'teff2' in samples.dtype.names or 'logg2' in samples.dtype.names or 'rad2' in samples.dtype.names:
         pars1 = []
         for p in ['teff', 'logg', 'rad', 'teff2', 'logg2', 'rad2']:
            if p in samples.dtype.names: pars1.append(p)
         
         data = samples[pars1]
         fig = corner.corner(data.view(np.float64).reshape(data.shape + (-1,)), 
                       labels = data.dtype.names,
                       quantiles=[0.025, 0.16, 0.5, 0.84, 0.975],
                       levels=[0.393, 0.865, 0.95],
                       show_titles=True, title_kwargs={"fontsize": 12})
         if plotpath:
            pl.savefig(plotpath + '/distribution_primary.png')
         
         pars2 = []
         for p in ['mass', 'L', 'mass2', 'L2', 'q', 'd']:
            if p in samples.dtype.names: pars2.append(p)
      
         data = samples[pars2]
         fig = corner.corner(data.view(np.float64).reshape(data.shape + (-1,)), 
                       labels = data.dtype.names,
                       quantiles=[0.025, 0.16, 0.5, 0.84, 0.975],
                       levels=[0.393, 0.865, 0.95],
                       show_titles=True, title_kwargs={"fontsize": 12})
         if plotpath:
            pl.savefig(plotpath + '/distribution_derived.png')
      
      else:
         pars1 = []
         for p in ['teff', 'logg', 'rad', 'mass', 'L', 'd']:
            if p in samples.dtype.names: pars1.append(p)
            
         data = samples[pars1]
         fig = corner.corner(data.view(np.float64).reshape(data.shape + (-1,)), 
                       labels = data.dtype.names,
                       quantiles=[0.025, 0.16, 0.5, 0.84, 0.975],
                       levels=[0.393, 0.865, 0.95],
                       show_titles=True, title_kwargs={"fontsize": 12})
         if plotpath:
            pl.savefig(plotpath + '/distribution_primary.png')
      
      pl.show()