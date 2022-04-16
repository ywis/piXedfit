import numpy as np 
from math import sqrt
import sys
from operator import itemgetter
from astropy.io import fits

__all__ = ["pixel_binning_photo"]


def old_pixel_binning_photo(flux_map_fits=None, filters=None, ref_band=None, Dmin_bin=2.0, SNR=[], 
	redc_chi2_limit=4.0, sys_err_factor=0.0, name_out_fits=None):
	"""A function for conducting pixel binning to maximize the S/N of spatially resolved SEDs.

	:param flux_map_fits:
		An input FITS file containing the maps of multiband fluxes and fluxes uncertainties.
		This FITS file should be in the same format as that produced using the :py:func:`flux_map` function in the :py:mod:`piXedfit_images` module

	:param filters: (default: None)
		A list of filters (in string) that will be consider in the pixel binning process, especially in the SED shape similarity evaluation.
		If filters=None, the original filters list (stored in the flux_map_fits FITS file) is used.

	:param ref_band: (default: None)
		Index of a band/filter to be used as reference in sorting pixels based on their brightness.
		If ref_band=None, the ref_band is taken to be the middle band in the list of filters considered for the pixel binning.

	:param Dmin_bin: (default: 2.0 pixels)
		Minimum diameter of a bin in unit of pixel.

	:param SNR: (default: [])
		An array/list containing S/N raatio thresholds of the filters. This array should has the same length as that of the 
		input filters (input filters!=None) or the set of original filters (if input filters==None). S/N threshold can vary across
		the filters. If SNR is empty (for some reasons), S/N of 5 is applied to all the filters. 

	:param redc_chi2_limit: (default: 4.0)
		A maximum reduced chi-square in which two SED are considered to have similar SED shape. 

	:param sys_err_factor: (optional, default: 0.0)
		An estimate for systematic error of the input fluxes maps, in which the bulk is assumed to be a factor of the flux (in every band).

	:param name_out_fits: (defult: None)
		Desired name for the output FITS file.

	
	:returns name_out_fits: (optional)
		Desired name of output FITS file.
	"""

	# input FITS file:
	name_fits_in = flux_map_fits
	# name for the output FITS file: 
	if name_out_fits != None:
		name_out_fits = name_out_fits
	elif name_out_fits == None:
		name_out_fits = "pixbin_%s" % flux_map_fits
	# minimum diamater for bin (in unit of pixel):
	FWHM = Dmin_bin

	# desired structure: map_flux[idx-y][idx-x][idx-band]
	hdu = fits.open(name_fits_in)
	map_mask = hdu['galaxy_region'].data 
	map_flux = np.transpose(hdu['flux'].data, axes=(1, 2, 0))
	map_flux_err = np.transpose(hdu['flux_err'].data, axes=(1, 2, 0))

	map_flux_err = map_flux_err - (sys_err_factor*map_flux)

	header = hdu[0].header
	nbands_ori = int(header['nfilters'])
	# unit:
	unit = float(header['unit'])
	# dimension:
	dim_y = map_mask.shape[0]
	dim_x = map_mask.shape[1]
	print ("[Pixel binning for %s]" % name_fits_in)

	hdu.close()

	# get desired filters list to be considered in the pixel binning process, especilly in the evaluation of the SED shape similarity:
	if filters != None:
		nbands = len(filters)
		bands_id = np.zeros(nbands)
		for ii in range(0,nbands):
			for bb in range(0,nbands_ori):
				str_temp = 'fil%d' % bb
				if filters[ii] == header[str_temp]:
					bands_id[ii] = bb
	elif filters == None:
		nbands = nbands_ori
		bands_id = np.zeros(nbands)
		filters = []
		for bb in range(0,nbands):
			str_temp = 'fil%d' % bb
			bands_id[bb] = bb
			filters.append(header[str_temp])

	if len(SNR) != nbands:
		print ("Number of element in SNR should be the same as that in filters!")
		sys.exit()

	# rescaling the fluxes based on the unit:
	#map_flux = map_flux*unit
	#map_flux_err = map_flux_err*unit
	map_flux = map_flux
	map_flux_err = map_flux_err

	# get reference filter:
	if ref_band != None:
		band_ref = ref_band
	elif ref_band == None:
		band_ref = bands_id[int((nbands-1)/2)]

	# get S/N threshold for all filters:
	if len(SNR) == 0:
		SN_threshold = np.zeros(nbands)
		for bb in range(0,nbands):
			SN_threshold[bb] = 5.0
	elif len(SNR) > 0:
		if len(SNR)!=nbands:
			print ("Error: Number of element in SNR should be the same as the number of input filters")
		else:
			SN_threshold = SNR

	pix_flux_ref = []
	pix_x = []
	pix_y = []
	pixid_xy = np.zeros((dim_y,dim_x))
	idx_pix = 0
	for yy in range(0,dim_y):
		for xx in range(0,dim_x):
			if map_mask[yy][xx]==1:
				pix_x.append(xx)
				pix_y.append(yy)
				pix_flux_ref.append(map_flux[yy][xx][int(band_ref)])
				idx_pix = idx_pix + 1
				pixid_xy[yy][xx] = idx_pix     # the index is initialized from 1
	npixs = idx_pix
	print ("=> Number of pixels in the galaxy's region: %d" % npixs)

	# Pixel binning process:
	pix_bin_flag = np.zeros((dim_y,dim_x))
	count_bin = 0
	del_r = 2             				# radius increment in pixel
	status_process = 0
	bin_flux = []         				# bin_flux[idx_bin][idx_band]
	bin_flux_err = []     				# bin_flux_err[idx_bin][idx_band]
	cumul_npixs_bin = 0
	while status_process==0:
		# get central pixel for an incoming bin:
		idx0, max_val = max(enumerate(pix_flux_ref), key=itemgetter(1))
		xc_bin = pix_x[idx0]
		yc_bin = pix_y[idx0]

		# calculate radius of all the pixels:
		pix_x_norm = np.asarray(pix_x) - xc_bin
		pix_y_norm = np.asarray(pix_y) - yc_bin
		pix_rad = np.sqrt((pix_x_norm*pix_x_norm) + (pix_y_norm*pix_y_norm))

		SN = np.zeros(nbands)
		IDpix_bin_temp = []
		count_pix_bin = 0
		tot_flux_bin = np.zeros(nbands)
		tot_flux_err_bin = np.zeros(nbands)

		SN_cont = np.zeros(nbands)
		tot_flux_bin_cont = np.zeros(nbands)
		tot_flux_err_bin_cont = np.zeros(nbands)

		# make first circle:
		temp_pixid = 0
		count_pix_temp = 0
		rad0 = 0.5*FWHM
		for pp in range(0,npixs):
			x0 = pix_x[pp]
			y0 = pix_y[pp]
			if pix_rad[pp]<=rad0 and pix_bin_flag[int(y0)][int(x0)]==0:
				IDpix_bin_temp.append(pixid_xy[int(y0)][int(x0)])
				count_pix_bin = count_pix_bin + 1
				# modify the pixel's radius so it will not be selected again:
				pix_rad[pp] = dim_x*dim_x*dim_x + temp_pixid
				temp_pixid = temp_pixid + 1
				count_pix_temp = count_pix_temp + 1
				idx_temp = 0
				for bb in bands_id:
					temp = tot_flux_bin[int(idx_temp)]
					tot_flux_bin[int(idx_temp)] = temp + map_flux[int(y0)][int(x0)][int(bb)]
					temp = tot_flux_err_bin[int(idx_temp)]
					tot_flux_err_bin[int(idx_temp)] = temp + (map_flux_err[int(y0)][int(x0)][int(bb)]*map_flux_err[int(y0)][int(x0)][int(bb)])

					temp = tot_flux_bin_cont[int(idx_temp)]
					tot_flux_bin_cont[int(idx_temp)] = temp + map_flux[int(y0)][int(x0)][int(bb)]
					temp = tot_flux_err_bin_cont[int(idx_temp)]
					tot_flux_err_bin_cont[int(idx_temp)] = temp + (map_flux_err[int(y0)][int(x0)][int(bb)]*map_flux_err[int(y0)][int(x0)][int(bb)])

					idx_temp = idx_temp + 1

		# calculate S/N:
		#count_fit_SN = 0
		#count_fit_SN_cont = 0
		#for bb in range(0,nbands):
		#	SN[bb] = tot_flux_bin[bb]/math.sqrt(tot_flux_err_bin[bb])
		#	if SN[bb]>=SN_threshold[bb]:
		#		count_fit_SN = count_fit_SN + 1
		#		count_fit_SN_cont = count_fit_SN_cont + 1

		SN = tot_flux_bin/np.sqrt(tot_flux_err_bin)
		idx_sel = np.where(SN>=SN_threshold)
		count_fit_SN = len(idx_sel[0])
		count_fit_SN_cont = len(idx_sel[0])

		if count_fit_SN == nbands:
			status_SN = 1
		elif count_fit_SN < nbands:
			status_SN = 0

		if count_fit_SN_cont < nbands:
			status_SN_cont = 0
		elif count_fit_SN_cont >= nbands:
			status_SN_cont = 1

		while status_SN == 0:
			# queuing from pixel with smallest radius to pixel with largest radius:
			idx, min_val = min(enumerate(pix_rad), key=itemgetter(1))
			if pix_rad[idx]>rad0:
				x0 = pix_x[idx]
				y0 = pix_y[idx]

				# check for similarity of SED shape with the central pixel using chi-square:
				f1 = map_flux[int(yc_bin)][int(xc_bin)]
				f2 = map_flux[int(y0)][int(x0)]
				f1_err = map_flux_err[int(yc_bin)][int(xc_bin)]
				f2_err = map_flux_err[int(y0)][int(x0)]

				# select only photometric points that are positive:
				#idx_excld = np.where((f1<0) | (f2<0))
				#f1 = np.delete(f1, idx_excld[0])
				#f2 = np.delete(f2, idx_excld[0])
				#f1_err = np.delete(f1_err, idx_excld[0])
				#f2_err = np.delete(f2_err, idx_excld[0])

				aaa = np.sum(f2*f1/((f1_err*f1_err)+(f2_err*f2_err)))
				bbb = np.sum(f1*f1/((f1_err*f1_err)+(f2_err*f2_err)))
				norm_sed = aaa/bbb
				chi2 = np.sum((f2-(norm_sed*f1))*(f2-(norm_sed*f1))/((f1_err*f1_err)+(f2_err*f2_err)))

				if chi2/len(f1)<=redc_chi2_limit and pix_bin_flag[int(y0)][int(x0)]==0:
					IDpix_bin_temp.append(pixid_xy[int(y0)][int(x0)])
					count_pix_bin = count_pix_bin + 1

					idx_temp = 0
					for bb in bands_id:
						temp = tot_flux_bin[int(idx_temp)]
						tot_flux_bin[int(idx_temp)] = temp + map_flux[int(y0)][int(x0)][int(bb)]
						temp = tot_flux_err_bin[int(idx_temp)]
						tot_flux_err_bin[int(idx_temp)] = temp + (map_flux_err[int(y0)][int(x0)][int(bb)]*map_flux_err[int(y0)][int(x0)][int(bb)])
						idx_temp = idx_temp + 1

				if pix_bin_flag[int(y0)][int(x0)]==0:
					count_pix_temp = count_pix_temp + 1

					idx_temp = 0
					for bb in bands_id:
						temp = tot_flux_bin_cont[int(idx_temp)]
						tot_flux_bin_cont[int(idx_temp)] = temp + map_flux[int(y0)][int(x0)][int(bb)]
						temp = tot_flux_err_bin_cont[int(idx_temp)]
						tot_flux_err_bin_cont[int(idx_temp)] = temp + (map_flux_err[int(y0)][int(x0)][int(bb)]*map_flux_err[int(y0)][int(x0)][int(bb)])
						idx_temp = idx_temp + 1

			# update S/N:
			#count_fit_SN = 0
			#count_fit_SN_cont = 0
			#for bb in range(0,nbands):
			#	SN[bb] = tot_flux_bin[bb]/math.sqrt(tot_flux_err_bin[bb])
			#	SN_cont[bb] = tot_flux_bin_cont[bb]/math.sqrt(tot_flux_err_bin_cont[bb])
			#	if SN[bb]>=SN_threshold[bb]:
			#		count_fit_SN = count_fit_SN + 1
			#	if SN_cont[bb]>=SN_threshold[bb]:
			#		count_fit_SN_cont = count_fit_SN_cont + 1

			SN = tot_flux_bin/np.sqrt(tot_flux_err_bin)
			idx_sel = np.where(SN>=SN_threshold)
			count_fit_SN = len(idx_sel[0])

			SN_cont = tot_flux_bin_cont/np.sqrt(tot_flux_err_bin_cont)
			idx_sel = np.where(SN_cont>=SN_threshold)
			count_fit_SN_cont = len(idx_sel[0])

			if count_fit_SN == nbands:
				status_SN = 1
			if count_fit_SN_cont < nbands:
				status_SN_cont = 0

			# modify the pixel's radius so it will not be selected again:
			pix_rad[idx] = dim_x*dim_x*dim_x + temp_pixid
			temp_pixid = temp_pixid + 1

			if status_SN_cont==0 and count_pix_temp>=npixs-cumul_npixs_bin:
				status_process = 1
				break

			# end of while np.min(SN)<SN_threshold

		if status_process==0:
			count_bin = count_bin + 1
			cumul_npixs_bin = cumul_npixs_bin + count_pix_bin
			sys.stdout.write('\r')
			sys.stdout.write("=> Bin index=%d  number of pixels in the bin=%d  cumulative number of binned pixels=%d" % (count_bin,count_pix_bin,cumul_npixs_bin))
			sys.stdout.flush()

			# get total flux and flux error of the bin:
			temp_tot_flux = np.zeros(nbands_ori)
			temp_tot_flux_err = np.zeros(nbands_ori)
			for rr in range(0,count_pix_bin):
				idx0 = IDpix_bin_temp[int(rr)]
				x1 = pix_x[int(idx0)-1]
				y1 = pix_y[int(idx0)-1]
				pix_bin_flag[int(y1)][int(x1)] = count_bin
				pix_flux_ref[int(idx0)-1] = -1.0e+60
				for bb in range(0,nbands_ori):
					temp0 = temp_tot_flux[int(bb)]
					temp_tot_flux[bb] = temp0 + map_flux[int(y1)][int(x1)][bb]
					temp0 = temp_tot_flux_err[bb]
					temp_tot_flux_err[bb] = temp0 + (map_flux_err[int(y1)][int(x1)][bb]*map_flux_err[int(y1)][int(x1)][bb])

			bin_flux.append([])
			bin_flux_err.append([])
			for bb in range(0,nbands_ori):
				bin_flux[int(count_bin)-1].append(temp_tot_flux[bb])
				bin_flux_err[int(count_bin)-1].append(math.sqrt(temp_tot_flux_err[bb]))

		elif status_process == 1:
			# bin all remining pixels into one bin:
			flux_bin_temp = np.zeros(nbands_ori)
			flux_err_bin_temp = np.zeros(nbands_ori)
			count_pix_bin = 0
			for xx in range(0,dim_x):
				for yy in range(0,dim_y):
					if map_mask[yy][xx]==1 and pix_bin_flag[yy][xx]==0:
						pix_bin_flag[yy][xx] = count_bin + 1
						count_pix_bin = count_pix_bin + 1

						idx_temp = 0
						for bb in range(0,nbands_ori):
							temp = flux_bin_temp[bb]
							flux_bin_temp[bb] = temp + map_flux[yy][xx][bb]
							temp = flux_err_bin_temp[bb]
							flux_err_bin_temp[bb] = temp + (map_flux_err[yy][xx][bb]*map_flux_err[yy][xx][bb])
							idx_temp = idx_temp + 1

			# store the bin fluxes and flux errors in array:
			if count_pix_bin > 0:
				count_bin = count_bin + 1
				bin_flux.append([])
				bin_flux_err.append([])
				for bb in range(0,nbands_ori):
					bin_flux[int(count_bin)-1].append(flux_bin_temp[bb])
					bin_flux_err[int(count_bin)-1].append(math.sqrt(flux_err_bin_temp[bb]))

				cumul_npixs_bin = cumul_npixs_bin + count_pix_bin
				sys.stdout.write('\r')
				sys.stdout.write("=> Bin index=%d  number of pixels in the bin=%d  cumulative number of binned pixels=%d \n" % (count_bin,count_pix_bin,cumul_npixs_bin))
				sys.stdout.flush()
			break
		# End of while status_process==0:

	# store the results to fits file:
	unit_new = 100.0*unit
	pix_bin_fluxes = np.zeros((nbands_ori,dim_y,dim_x))
	pix_bin_flux_err = np.zeros((nbands_ori,dim_y,dim_x))
	for yy in range(0,dim_y):
		for xx in range(0,dim_x):
			if map_mask[yy][xx]==1 and pix_bin_flag[yy][xx]>0:
				idx_bin0 = pix_bin_flag[yy][xx]
				for bb in range(0,nbands_ori):
					pix_bin_fluxes[bb][yy][xx] = bin_flux[int(idx_bin0)-1][bb]*unit/unit_new
					pix_bin_flux_err[bb][yy][xx] = bin_flux_err[int(idx_bin0)-1][bb]*unit/unit_new

	hdul = fits.HDUList()
	hdr = fits.Header()
	hdr['nfilters'] = nbands_ori
	hdr['nfilters_bin'] = nbands
	hdr['refband'] = band_ref
	hdr['z'] = header['z']
	hdr['nbins'] = count_bin
	hdr['unit'] = unit_new
	hdr['bunit'] = 'erg/s/cm^2/A'
	hdr['struct'] = '(band,y,x)'
	hdr['fil_sampling'] = header['fil_sampling']
	hdr['pix_size'] = header['pix_size']
	hdr['fil_psfmatch'] = header['fil_psfmatch']
	hdr['psf_fwhm'] = header['psf_fwhm']

	# A list of original filters
	for bb in range(0,nbands_ori):
		str_temp = 'fil%d' % bb
		hdr[str_temp] = header[str_temp]
	# list of filters considered in the pixel binning process:
	for bb in range(0,nbands):
		str_temp = 'fil_bin%d' % bb
		hdr[str_temp] = filters[bb]

	primary_hdu = fits.PrimaryHDU(header=hdr)
	hdul.append(primary_hdu)
	# add pixel bin flag:
	hdul.append(fits.ImageHDU(pix_bin_flag, name='bin_map'))
	# add map of bin flux:
	hdul.append(fits.ImageHDU(pix_bin_fluxes, name='bin_flux'))
	# add map if bin flux error:
	hdul.append(fits.ImageHDU(pix_bin_flux_err, name='bin_fluxerr'))
	# write to fits file:
	hdul.writeto(name_out_fits, overwrite=True)

	return name_out_fits





def pixel_binning_photo(fits_fluxmap=None, ref_band=None, Dmin_bin=2.0, SNR=[], redc_chi2_limit=4.0, name_out_fits=None):

	hdu = fits.open(fits_fluxmap)
	gal_region = hdu['galaxy_region'].data
	map_flux = hdu['flux'].data
	map_flux_err = hdu['flux_err'].data 
	header = hdu[0].header
	hdu.close()

	# transpose from (wave,y,x) -> (y,x,wave)
	map_flux_trans = np.transpose(map_flux, axes=(1,2,0))
	map_flux_err_trans = np.transpose(map_flux_err, axes=(1,2,0))

	nbands = int(header['nfilters'])
	if ref_band == None:
		ref_band = int((nbands-1)/2)
	else:
		ref_band = int(ref_band)

	if len(SNR)==0:
		SN_threshold = np.zeros(nbands)+5.0
	elif len(SNR) != nbands:
		print ("Number of elements in SNR should be the same as the number of filters in the fits_fluxmap!")
		sys.exit()
	else:
		SN_threshold = np.asarray(SNR) 

	dim_y = gal_region.shape[0]
	dim_x = gal_region.shape[1]

	pixbin_map = np.zeros((dim_y,dim_x))
	map_bin_flux = np.zeros((dim_y,dim_x,nbands))
	map_bin_flux_err = np.zeros((dim_y,dim_x,nbands))

	rows, cols = np.where((gal_region==1) & (pixbin_map==0))
	tot_npixs = len(rows)

	count_bin = 0
	del_r = 2
	cumul_npixs_in_bin = 0
	while len(rows)>0:
		# center pixel of a bin
		idx = np.unravel_index(map_flux[ref_band][rows,cols].argmax(), map_flux[ref_band][rows,cols].shape)
		bin_y_cent, bin_x_cent = rows[idx[0]], cols[idx[0]]

		#=> first circle
		bin_rad = 0.5*Dmin_bin
		del_dim = bin_rad + 3
		xmin = int(bin_x_cent-del_dim)
		xmax = int(bin_x_cent+del_dim)
		ymin = int(bin_y_cent-del_dim)
		ymax = int(bin_y_cent+del_dim)

		if xmin<0:
			xmin = 0
		if xmax>=dim_x:
			xmax = dim_x-1

		if ymin<0:
			ymin = 0
		if ymax>=dim_y:
			ymax = dim_y-1 

		x = np.linspace(xmin,xmax,xmax-xmin+1)
		y = np.linspace(ymin,ymax,ymax-ymin+1)
		xx, yy = np.meshgrid(x,y)

		crop_gal_region = gal_region[ymin:ymax+1,xmin:xmax+1]
		crop_pixbin_map = pixbin_map[ymin:ymax+1,xmin:xmax+1]

		data2D_rad = np.sqrt(np.square(xx-bin_x_cent) + np.square(yy-bin_y_cent))
		rows1, cols1 = np.where((data2D_rad<=bin_rad) & (crop_gal_region==1) & (crop_pixbin_map==0))

		rows1 = rows1 + ymin
		cols1 = cols1 + xmin

		# check S/N
		tot_bin_flux = np.zeros(nbands)
		tot_bin_flux_err2 = np.zeros(nbands)
		for bb in range(0,nbands):
			vals = map_flux[bb][rows1,cols1]
			vals = vals[np.logical_not(np.isnan(vals))] 
			#tot_bin_flux[bb] = np.sum(map_flux[bb][rows1,cols1])
			tot_bin_flux[bb] = np.sum(vals)

			vals = map_flux_err[bb][rows1,cols1]
			vals = vals[np.logical_not(np.isnan(vals))]
			#tot_bin_flux_err2[bb] = np.sum(np.square(map_flux_err[bb][rows1,cols1]))
			tot_bin_flux_err2[bb] = np.sum(np.square(vals)) 

		tot_SNR = tot_bin_flux/np.sqrt(tot_bin_flux_err2)
		idx0 = np.where(tot_SNR-SN_threshold>=0)

		if len(idx0[0]) == nbands:
			# get bin
			count_bin = count_bin + 1
			pixbin_map[rows1,cols1] = count_bin
			map_bin_flux[rows1,cols1] = tot_bin_flux
			map_bin_flux_err[rows1,cols1] = np.sqrt(tot_bin_flux_err2)
			cumul_npixs_in_bin = cumul_npixs_in_bin + len(rows1)

		#=> increase radius of the circle
		else:
			stat_increase = 1
			cumul_rows = rows1.tolist()
			cumul_cols = cols1.tolist()
			while stat_increase==1:
				rmin = bin_rad
				rmax = rmin + del_r

				del_dim = bin_rad + 3
				xmin = int(bin_x_cent-del_dim)
				xmax = int(bin_x_cent+del_dim)
				ymin = int(bin_y_cent-del_dim)
				ymax = int(bin_y_cent+del_dim)

				if xmin<0:
					xmin = 0
				if xmax>=dim_x:
					xmax = dim_x-1

				if ymin<0:
					ymin = 0
				if ymax>=dim_y:
					ymax = dim_y-1 

				x = np.linspace(xmin,xmax,xmax-xmin+1)
				y = np.linspace(ymin,ymax,ymax-ymin+1)
				xx, yy = np.meshgrid(x,y)

				crop_gal_region = gal_region[ymin:ymax+1,xmin:xmax+1]
				crop_pixbin_map = pixbin_map[ymin:ymax+1,xmin:xmax+1]

				data2D_rad = np.sqrt(np.square(xx-bin_x_cent) + np.square(yy-bin_y_cent))
				rows1, cols1 = np.where((data2D_rad>rmin) & (data2D_rad<=rmax) & (crop_gal_region==1) & (crop_pixbin_map==0))

				rows1 = rows1 + ymin
				cols1 = cols1 + xmin

				cumul_rows = cumul_rows + rows1.tolist()
				cumul_cols = cumul_cols + cols1.tolist()

				# check S/N
				tot_bin_flux = np.zeros(nbands)
				tot_bin_flux_err2 = np.zeros(nbands)
				for bb in range(0,nbands):
					vals = map_flux[bb][rows1,cols1]
					vals = vals[np.logical_not(np.isnan(vals))]
					temp = tot_bin_flux[bb]
					#tot_bin_flux[bb] = temp + np.sum(map_flux[bb][rows1,cols1])
					tot_bin_flux[bb] = temp + np.sum(vals)

					vals = map_flux_err[bb][rows1,cols1]
					vals = vals[np.logical_not(np.isnan(vals))]
					temp = tot_bin_flux_err2[bb]
					#tot_bin_flux_err2[bb] = temp + np.sum(np.square(map_flux_err[bb][rows1,cols1])) 
					tot_bin_flux_err2[bb] = temp + np.sum(np.square(vals))


				tot_SNR = tot_bin_flux/np.sqrt(tot_bin_flux_err2)
				idx0 = np.where(tot_SNR-SN_threshold>=0)

				if len(idx0[0]) == nbands:
					# get bin
					count_bin = count_bin + 1
					pixbin_map[cumul_rows,cumul_cols] = count_bin
					map_bin_flux[cumul_rows,cumul_cols] = tot_bin_flux
					map_bin_flux_err[cumul_rows,cumul_cols] = np.sqrt(tot_bin_flux_err2)
					cumul_npixs_in_bin = cumul_npixs_in_bin + len(cumul_rows)

					stat_increase = 0
				
				else:
					if (len(cumul_rows)+cumul_npixs_in_bin) == tot_npixs:
						# get bin
						count_bin = count_bin + 1
						pixbin_map[cumul_rows,cumul_cols] = count_bin
						map_bin_flux[cumul_rows,cumul_cols] = tot_bin_flux
						map_bin_flux_err[cumul_rows,cumul_cols] = np.sqrt(tot_bin_flux_err2)
						cumul_npixs_in_bin = cumul_npixs_in_bin + len(cumul_rows)

						stat_increase = 0
						break
					else:
						stat_increase = 1


				bin_rad = bin_rad + del_r


		rows, cols = np.where((gal_region==1) & (pixbin_map==0))
		# end of while..


	print ("Number of bins: %d" % count_bin)
	# transpose from (y,x,wave) => (wave,y,x)
	map_bin_flux_trans = np.transpose(map_bin_flux, axes=(2,0,1))
	map_bin_flux_err_trans = np.transpose(map_bin_flux_err, axes=(2,0,1))

	## store into FITS file
	hdul = fits.HDUList()
	hdr = fits.Header()
	hdr['nfilters'] = nbands
	hdr['refband'] = ref_band
	hdr['z'] = header['z']
	hdr['nbins'] = count_bin
	hdr['unit'] = header['unit']
	hdr['bunit'] = 'erg/s/cm^2/A'
	hdr['struct'] = '(band,y,x)'
	hdr['fil_sampling'] = header['fil_sampling']
	hdr['pix_size'] = header['pix_size']
	hdr['fil_psfmatch'] = header['fil_psfmatch']
	hdr['psf_fwhm'] = header['psf_fwhm']

	for bb in range(0,nbands):
		str_temp = 'fil%d' % bb
		hdr[str_temp] = header[str_temp]

	primary_hdu = fits.PrimaryHDU(header=hdr)
	hdul.append(primary_hdu)
	hdul.append(fits.ImageHDU(pixbin_map, name='bin_map'))
	hdul.append(fits.ImageHDU(map_bin_flux_trans, name='bin_flux'))
	hdul.append(fits.ImageHDU(map_bin_flux_err_trans, name='bin_fluxerr'))

	if name_out_fits == None:
		name_out_fits = "pixbin_%s" % fits_fluxmap

	hdul.writeto(name_out_fits, overwrite=True)

	return name_out_fits



























