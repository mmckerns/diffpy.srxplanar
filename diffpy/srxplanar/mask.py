#!/usr/bin/env python
##############################################################################
#
# diffpy.srxplanar  by DANSE Diffraction group
#                   Simon J. L. Billinge
#                   (c) 2010 Trustees of the Columbia University
#                   in the City of New York.  All rights reserved.
#
# File coded by:    Xiaohao Yang
#
# See AUTHORS.txt for a list of people who contributed.
# See LICENSE.txt for license information.
#
##############################################################################

import numpy as np
import scipy.sparse as ssp
try:
    import fabio
    def openImage(im):
        rv = fabio.openimage.openimage(im)
        return rv.data
except:
    import tifffile
    print 'Only tiff or .npy mask is support since fabio is not available'
    def openImage(im):
        try:
            rv = tifffile.imread(im)
        except:
            rv = 0
        return rv

import scipy.ndimage.filters as snf
import scipy.ndimage.morphology as snm
import os
from diffpy.srxplanar.srxplanarconfig import _configPropertyR

class Mask(object):
    '''
    provide methods for mask generation, including:
    
    static mask: fit2d (.msk) mask, tif mask, npy mask
    dymanic mask: masking dark pixels, bright pixels
    
    *fit2d mask if supported through Fabio
    '''

    xdimension = _configPropertyR('xdimension')
    ydimension = _configPropertyR('ydimension')
    fliphorizontal = _configPropertyR('fliphorizontal')
    flipvertical = _configPropertyR('flipvertical')
    wavelength = _configPropertyR('wavelength')
    maskfile = _configPropertyR('maskfile')
    brightpixelmask = _configPropertyR('brightpixelmask')
    darkpixelmask = _configPropertyR('darkpixelmask')
    
    def __init__(self, p):
        self.config = p
        return

    def staticMask(self, maskfile=None):
        '''
        create a static mask according existing mask file. This mask remain unchanged for different images
        
        :param maskfile: string, file name of mask, 
            mask file supported: .msk, .npy, .tif file, ATTN: mask in .npy form should be already flipped, 
            and 1 (or larger) stands for masked pixels, 0(<0) stands for unmasked pixels
        
        :return: 2d array of boolean, 1 stands for masked pixel
        '''
        maskfile = self.maskfile if maskfile == None else maskfile

        # fit2d mask
        if os.path.exists(maskfile):
            if maskfile.endswith('.msk'):
                # rv += self.flipImage(immask.data)
                rv = openImage(maskfile)
            elif maskfile.endswith('.npy'):
                rv = np.load(maskfile)
            elif maskfile.endswith('.tif'):
                immask = openImage(maskfile)
                rv = self.flipImage(immask)
        else:
            rv = np.zeros((self.ydimension, self.xdimension))

        self.staticmask = (rv > 0)
        return self.staticmask

    def dynamicMask(self, pic, brightpixelmask=None, darkpixelmask=None):
        '''
        create a dynamic mask according to image array. This mask changes for different images
        
        :param pic: 2d array, image array to be processed
        :param brightpixelmask: pixels with much lower intensity compare to adjacent pixels will be masked
        :param darkpixelmask: pixels with much higher intensity compare to adjacent pixels will be masked
             
        :return: 2d array of boolean, 1 stands for masked pixel
        '''
        
        brightpixelmask = self.brightpixelmask if brightpixelmask == None else brightpixelmask
        darkpixelmask = self.darkpixelmask if darkpixelmask == None else darkpixelmask
        
        if darkpixelmask or brightpixelmask:
            rv = np.zeros((self.ydimension, self.xdimension))
            if darkpixelmask:
                rv += self.darkPixelMask(pic)
            if brightpixelmask:
                rv += self.brightPixelMask(pic)
            self.dynamicmask = (rv > 0)    
        else:
            self.dynamicmask = None
        return self.dynamicmask

    def darkPixelMask(self, pic, r=None):
        '''
        pixels with much lower intensity compare to adjacent pixels will be masked
        
        :param pic: 2d array, image array to be processed
        :param r: float, a threshold for masked pixels
        
        :return: 2d array of boolean, 1 stands for masked pixel
        '''
        r = self.config.darkpixelr if r == None else r  # 0.1
        
        avgpic = np.average(pic)
        ks = np.ones((5, 5))
        ks1 = np.ones((7, 7))
        picb = snf.percentile_filter(pic, 5, 3) < avgpic * r
        picb = snm.binary_dilation(picb, structure=ks)
        picb = snm.binary_erosion(picb, structure=ks1)
        return picb

    def brightPixelMask(self, pic, size=None, r=None):
        '''
        pixels with much higher intensity compare to adjacent pixels will be masked,
        this mask is used when there are some bright spots/pixels whose intensity is higher 
        than its neighbors but not too high. Only use this on a very good powder averaged 
        data. Otherwise it may mask wrong pixels. 
        
        This mask has similar functions as 'selfcorr' function. However, this mask will only 
        consider pixels' local neighbors pixels and tend to mask more pixels. While 'selfcorr' 
        function compare one pixel to other pixels in same bin.
        
        :param pic: 2d array, image array to be processed
        :param size: int, size of local testing area
        :param r: float, a threshold for masked pixels   
        
        :return: 2d array of boolean, 1 stands for masked pixel
        '''
        size = self.config.brightpixelsize if size == None else size  # 5
        r = self.config.brightpixelr if r == None else r  # 1.2
        
        rank = snf.rank_filter(pic, -size, size)
        ind = snm.binary_dilation(pic > rank * r, np.ones((3, 3)))
        return ind

    def undersample(self, undersamplerate):
        '''
        a special mask used for undesampling image. It will create a mask that
        discard (total number*(1-undersamplerate)) pixels
        :param undersamplerate: float, 0~1, ratio of pixels to keep
        
        :return: 2d array of boolean, 1 stands for masked pixel
        '''
        mask = np.random.rand(self.ydimension, self.xdimension) < undersamplerate
        return mask

    def flipImage(self, pic):
        '''
        flip image if configured in config
        
        :param pic: 2d array, image array
        
        :return: 2d array, flipped image array
        '''
        if self.fliphorizontal:
            pic = pic[:, ::-1]
        if self.flipvertical:
            pic = pic[::-1, :]
        return pic

    def saveMask(self, filename, pic=None, addmask=None):
        '''
        generate a mask according to the addmask and pic. save it to .npy. 1 stands for masked pixel
        the mask has same order as the pic, which means if the pic is flipped, the mask is fliped
        (when pic is loaded though loadimage, it is flipped)
        
        :param filename: str, filename of mask file to be save
        :param pic: 2d array, image array
        :param addmask: list of str, control which mask to generate
        
        :return: 2d array of boolean, 1 stands for masked pixel
        '''
        if not hasattr(self, 'mask'):
            self.normalMask(addmask)
        if (not hasattr(self, 'dynamicmask')) and (pic != None):
            self.dynamicMask(pic, addmask=addmask)
        tmask = self.mask
        if hasattr(self, 'dynamicmask'):
            if self.dynamicmask != None:
                tmask = np.logical_or(self.mask, self.dynamicmask) if pic != None else self.mask
        np.save(filename, tmask)
        return tmask
