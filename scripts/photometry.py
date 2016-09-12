#!/usr/bin/env python

"""
    --------------------------------------------------------------------------
    Routine to perform aperture photometry on CHIMERA science frames.
    
    Usage: python photometry.py [options] image coords
        
                                
    Author:
        Navtej Saini

    Organization:
        Caltech, Pasadena, CA, USA

    Version:
        20 December 2015     0.1dev     Initial implementation 
         9 Feb 2016          0.2        User can input photometric zero point
    --------------------------------------------------------------------------        
"""

import os, sys
from pyraf import iraf
import numpy as np, warnings
from StringIO import StringIO
from optparse import OptionParser

try:
    import matplotlib.pylab as plt
except ImportError:
    plot_flag = False
else:
    try:
        import seaborn
    except ImportError:
        pass
    plot_flag = True


import chimera



def dump(infile, keywords):
    """
    Dump keyword data from DAOPHOT output photometry file.
        
    Parameters
    ----------
    keywords : string
        Comma separated fields that have to be extracted from phot file
            
    Returns
    -------
    indata : numpy array
        Photometry data array    
    """
    # Load iraf packages
    iraf.noao(_doprint = 0)
    iraf.noao.digiphot(_doprint = 0)
    iraf.noao.digiphot.ptools(_doprint = 0)
    
    indata = iraf.pdump(infile, keywords, "yes", Stdout = 1)
    
    return indata[1]
        

def plotter(phot_data, nframes, exptime, outfile):
    """
    Plot light curve. 
    
    Parameters
    ----------
    phot_data : numpy array
        Photometry array
        
    nframes : int
        Number of image cube frames
        
    exptime : float
        Kinetic or accumulation time
        
    outfile : string
        Name of the out png image
        
    Returns
    -------
    None
    """   
    params = {'backend': 'ps',
	      'font.size': 10,
              'axes.labelweight': 'medium',
	      'figure.dpi' : 300,
              'savefig.dpi': 300,
              'savefig.jpeg_quality': 100
              }
    plt.rcParams.update(params)
	   
    ts = np.linspace(0, nframes*exptime, nframes)       
    plt.figure(figsize=(6,4))
    plt.title("Normalized Light Curve : %s" %phot_data[0]['DATETIME'].split('T')[0])
    plt.xlabel("Time (secs)")
    plt.ylabel("Normalized Flux")
    #dt = [item.split('T')[1] for item in phot_data['DATETIME']]
    #plt.xticks(np.arange(min(ts), max(ts)+10, 60), dt, rotation = 45)
    plt.plot(ts, phot_data['FLUX_ADU']/np.mean(phot_data['FLUX_ADU']), "r-")    
    plt.savefig(outfile, dpi = 300, bbox_inches = "tight")
    
    return
                
                                
def process(infile, coords, fwhmpsf, sigma, aperture, annulus, dannulus, output, zmag, debug):
    """
    Entry point function to process science image.
    
    Parameters
    ----------
    infile : string
        Science image or list of science images
        
    coords : string
        Input text file with coordinates of stars
        
    fwhmpsf : float
        FWHM of the stelar psf in pixels
        
    sigma : float
        Sky background sigma
        
    annulus : int
        Inner sky annulus radius in pixels
        
    dannulus : int
        Radius of sky annulus in pixels 
        
    output : string
        Output file name
        
    zmag : string
        Photometric zero point
                
    Returns
    -------
    None 
    """
    print "PHOTOMETRY: CHIMERA Aperture Photometry Routine"
    
    fwhmpsf = float(fwhmpsf)
    sigma = float(sigma)
    annulus = int(annulus)
    dannulus = int(dannulus)
    
    # Check if input is a string of FITS images or a text file with file names
    if infile[0] == "@":
        infile = infile[1:]
        
        if not os.path.exists(infile):
            raise IOError("PHOTOMETRY: Not able to locate file %s. Stopping." %infile)
        
        image_cubes = []
        with open(infile, "r") as fd:
            for line in fd.readlines():
                if len(line) > 1:
                    image_cubes.append(line.replace("\n", ""))
    else:
        image_cubes = infile.split(",")

    # Number of images
    ncubes = len(image_cubes)

    # Check if the input coordinates file exists. Take a tmp copy of the input
    # file and use that. Delete at the end of processing.
    if not os.path.exists(coords):
        raise IOError("Input coordinate file %s does not exist. Stopping." %coords)
    else:
        tmp_coords = coords + ".tmp"
        iraf.copy(coords, tmp_coords)
    

    # Fields to extract from phot file
    fields = "XCEN,YCEN,CIER,MSKY,STDEV,NSKY,SIER,SUM,AREA,FLUX,MERR,PIER"

    total_phot_data = []
    img_sec = []
    for i in range(ncubes):
        sci_file = image_cubes[i]
        
        if not os.path.exists(sci_file):
            raise IOError("FITS image %s does not exist. Stopping." %sci_file)
        
        fpath, fname = os.path.split(sci_file)
        
        print "\n  Processing science image %s" %fname

        # Instantiate an Aperphot object
        ap = chimera.Aperphot(sci_file, coords)
        
        # Set fwhmpsf, sigma, annulus. dannulus and zero point
        ap.fwhmpsf = fwhmpsf
        ap.sigma = sigma
        ap.annulus = annulus
        ap.dannulus = dannulus
        
        if zmag != "":
            ap.zmag = float(zmag)
        
        # Read the input FITS image
        if i == 0:
            img, imghdr = chimera.fitsread(ap.sci_file, header = True)
        else:
            img = chimera.fitsread(ap.sci_file)

        
        # Determine nominal aperture radius for photometry
        if i == 0:
            if aperture:
                nom_aper = float(aperture)
            else:
                nom_aper = ap.daocog()
            
            print "  Nominal aperture radius : %4.1f pixels" %nom_aper
           
           
        # Perform aperture photometry on all the frames
        dtype = [("DATETIME", "S25"),("XCEN", "f4"),("YCEN", "f4"),("CIER", "i4"),("MSKY", "f4"),("STDEV", "f4"),("NSKY", "i4"),("SIER", "i4"),("SUM", "f4"),("AREA", "f4"),("FLUX_ADU", "f4"),("FLUX_ELEC", "f4"),("FERR", "f4"),("MAG", "f4"),("MERR", "f4"),("PIER", "i4"),]
        phot_data = np.zeros([ap.nframes], dtype = dtype)
        for j in range(ap.nframes):
            print "    Processing frame number : %d" %(j+1)
             
            outfile = sci_file.replace(".fits", "_" + str(j) + ".phot.1")
            ap.daophot(j+1, tmp_coords, outfile, nom_aper)
            objcen = dump(outfile, "XCEN,YCEN")
            with open(tmp_coords, "w") as fd:
                fd.write(objcen + '\n')
            
            aperphot_data = dump(outfile, fields).split()
            
            phot_data[j]['DATETIME'] = ap.addtime(j * ap.kintime).isoformat()
            phot_data[j]['XCEN'] = float(aperphot_data[0])
            phot_data[j]['YCEN'] = float(aperphot_data[1])
            phot_data[j]['CIER'] = int(aperphot_data[2])
            phot_data[j]['MSKY'] = float(aperphot_data[3])
            phot_data[j]['STDEV'] = float(aperphot_data[4])
            phot_data[j]['NSKY'] = int(aperphot_data[5])
            phot_data[j]['SIER'] = int(aperphot_data[6])
            phot_data[j]['SUM'] = float(aperphot_data[7])
            phot_data[j]['AREA'] = float(aperphot_data[8])
            phot_data[j]['FLUX_ADU'] = float(aperphot_data[9])
            phot_data[j]['FLUX_ELEC'] = float(aperphot_data[9]) * ap.epadu
            phot_data[j]['MAG'] = ap.zmag - 2.5 * np.log10(phot_data[j]['FLUX_ELEC']/ap.exptime)
            if aperphot_data[10] == 'INDEF':
                phot_data[j]['MERR'] = -10
            else:
                phot_data[j]['MERR'] = float(aperphot_data[10])
            phot_data[j]['PIER'] = int(aperphot_data[11])
            
            # Calculate error in flux - using the formula
            # err = sqrt(flux * gain + npix * (1 + (npix/nsky)) * (flux_sky * gain + R**2))
            phot_data[j]['FERR'] = np.sqrt(phot_data[j]['FLUX_ELEC'] + phot_data[j]['AREA'] * (1 + phot_data[j]['AREA']/phot_data[j]['NSKY']) * (phot_data[j]['MSKY'] * ap.epadu + ap.readnoise**2))
                      
            # Save a 51x51 image section of the object
            xmin, xmax = int(phot_data[j]['XCEN']) - 25, int(phot_data[j]['XCEN']) + 25
            ymin, ymax = int(phot_data[j]['YCEN']) - 25, int(phot_data[j]['YCEN']) + 25            
            
            img_sec.append(img[j, ymin:ymax, xmin:xmax])


        # Save photometry of all the image cubes in a single file
        total_phot_data.append(phot_data)
                
        # If debug mode -
        # 1. save DAOPHOT phot files
        # 2. save individual phot data as npy file
        # 3. Plot light cuve for each data cube separatly
        
        if debug:
            # Save photometry data in numpy binary format
            print "  Saving photometry data as numpy binary"
            if output != "":
                npy_outfile = output + ".npy"
            else:
                npy_outfile = coords + "_phot.npy"
        
            if os.path.exists(npy_outfile):
                os.remove(npy_outfile)
            
            np.save(npy_outfile, phot_data)

        
            # Plot first pass light curve
            if plot_flag:
                print "  Plotting normalized light curve"
                if output != "":
                    plt_outfile = output + ".png"
                else:
                    plt_outfile = coords + "_lc.png"
                plotter(phot_data, ap.nframes, ap.kintime, plt_outfile)
        else:
            # Delete intermediate files is not debug mode
            iraf.delete(os.path.join(fpath, '*.phot.1'))    
                    
    # Convert the total_phot_data to array and reshape it
    print '  Saving consolidated photometry data...'
    total_phot_data_arr = np.concatenate(total_phot_data)
        
    # Save the array as npy file
    np.save(coords + "_total.phot.npy", total_phot_data_arr)

    # Save the image section with object as FITS file
    print '  Saving image section with object as FITS image...'
    img_sec_arr = np.asarray(img_sec)

    img_fname = coords + "_obj.fits"
    if os.path.exists(img_fname):
        os.remove(img_fname)
            
    chimera.fitswrite(img_sec_arr, coords + "_obj.fits", header = imghdr)
                        
    # Delete temporary coordinate file
    if os.path.exists(tmp_coords):
        os.remove(tmp_coords)
    
    return


if __name__ == "__main__":
    usage = "Usage: python %prog [options] sci_image coords"
    description = "Description. Utility to perform aperture photometry in CHIMERA science images."
    parser = OptionParser(usage = usage, version = "%prog 0.2", description = description)
    parser.add_option("-v", "--verbose",
                      action="store_true", dest="verbose", default = False,
                      help = "print result messages to stdout"
                      )
    parser.add_option("-q", "--quiet",
                    action="store_false", dest="verbose", default = True,
                    help = "don't print result messages to stdout"
                    )
    parser.add_option("-f", "--fwhmpsf", dest = "fwhmpsf",
                    action="store", metavar="FWHMPSF", help = "FWHM of PSF (default is 6 pixels)",
                    default = 6
                    )
    parser.add_option("-s", "--sigma", dest = "sigma",
                    action="store", metavar="SIGMA", help = "Sky background sigma (default is 10)",
                    default = 10
                    )
    parser.add_option("-a", "--aperture", dest = "aperture",
                    action="store", metavar="APERTURE", help = "Photometry aperture radius (default is None)",
                    default = None
                    )                    
    parser.add_option("-r", "--annulus", dest = "annulus",
                    action="store", metavar="ANNULUS", help = "Inner radius of sky annlus in pixels (default is 14)",
                    default = 14
                    )
    parser.add_option("-d", "--dannulus", dest = "dannulus",
                    action="store", metavar="DANNULUS", help = "Radius of sky annulus in piexls (default is 16)",
                    default = 16
                    )
    parser.add_option("-o", "--output", dest = "output",
                    action="store", metavar="OUTPUT", help = "Output file name",
                    default=""
                    ) 
    parser.add_option("-z", "--zmag", dest = "zmag",
                    action="store", metavar="ZMAG", help = "Photometric zero point",
                    default = ""
                    )   
    parser.add_option("-b", "--debug", dest = "debug",
                    action="store", metavar="DEBUG", help = "Debug modes? Default is False",
                    default = False
                    )                           
                                                                
                                        
    (options, args) = parser.parse_args()  
    if len(args) != 2:
        parser.error("PHOTOMETRY: Incorrect number of arguments")
        
    # Check verbosity
    if not options.verbose:
        output = StringIO()
        old_stdout = sys.stdout
        sys.stdout = output
 
    # Switch off warnings
    warnings.filterwarnings('ignore')
    
    process(args[0], args[1], options.fwhmpsf, options.sigma, options.aperture, options.annulus, options.dannulus, options.output, options.zmag, options.debug)    

    # Reset verbosity
    if not options.verbose:
        sys.stdout = old_stdout
