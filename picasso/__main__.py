#!/usr/bin/env python
"""
    ..__main__.py
    ~~~~~~~~~~~~~~~~

    Picasso command line interface

    :author: Joerg Schnitzbauer, Maximilian Thomas Strauss, 2016-2018
    :copyright: Copyright (c) 2016-2018 Jungmann Lab, MPI of Biochemistry
"""
import os.path
from picasso.gui import average


def _average(args):
    from glob import glob
    from .io import load_locs, NoMetadataFileError

    kwargs = {'iterations': args.iterations,
              'oversampling': args.oversampling}
    paths = glob(args.file)
    if paths:
        for path in paths:
            print('Averaging {}'.format(path))
            try:
                locs, info = load_locs(path)
            except NoMetadataFileError:
                continue
            kwargs['path_basename'] = os.path.splitext(path)[0] + '_avg'
            average(locs, info, **kwargs)


def _hdf2visp(path, pixel_size):
    from glob import glob
    paths = glob(path)
    if paths:
        from .io import load_locs
        import os.path
        from numpy import savetxt
        for path in paths:
            print('Converting {}'.format(path))
            locs, info = load_locs(path)
            locs = locs[['x', 'y', 'z', 'photons', 'frame']].copy()
            locs.x *= pixel_size
            locs.y *= pixel_size
            outname = os.path.splitext(path)[0] + '.3d'
            savetxt(outname, locs, fmt=['%.1f', '%.1f', '%.1f', '%.1f', '%d'],
                    newline='\r\n')


def _csv2hdf(path, pixelsize):
    from glob import glob
    from tqdm import tqdm as _tqdm
    paths = glob(path)
    if paths:
        from .io import save_locs
        import os.path
        import numpy as _np
        from numpy import savetxt
        for path in _tqdm(paths):
            print('Converting {}'.format(path))

            data = _np.genfromtxt(path, dtype=float, delimiter=',', names=True)

            try:
                frames = data['frame'].astype(int)
                # make sure frames start at zero:
                frames = frames - _np.min(frames)
                x = data['x_nm']/pixelsize
                y = data['y_nm']/pixelsize
                photons = data['intensity_photon'].astype(int)

                bg = data['offset_photon'].astype(int)
                lpx = data['uncertainty_xy_nm']/pixelsize
                lpy = data['uncertainty_xy_nm']/pixelsize

                if 'z_nm' in data.dtype.names:
                    z = data['z_nm']/pixelsize
                    sx = data['sigma1_nm']/pixelsize
                    sy = data['sigma2_nm']/pixelsize

                    LOCS_DTYPE = [('frame', 'u4'), ('x', 'f4'), ('y', 'f4'), ('z', 'f4'),
                      ('photons', 'f4'), ('sx', 'f4'), ('sy', 'f4'),
                      ('bg', 'f4'), ('lpx', 'f4'), ('lpy', 'f4')]

                    locs = _np.rec.array((frames, x, y, z, photons, sx, sy, bg, lpx, lpy),
                             dtype=LOCS_DTYPE)

                else:
                    sx = data['sigma_nm']/pixelsize
                    sy = data['sigma_nm']/pixelsize

                    LOCS_DTYPE = [('frame', 'u4'), ('x', 'f4'), ('y', 'f4'),
                      ('photons', 'f4'), ('sx', 'f4'), ('sy', 'f4'),
                      ('bg', 'f4'), ('lpx', 'f4'), ('lpy', 'f4')]

                    locs = _np.rec.array((frames, x, y, photons, sx, sy, bg, lpx, lpy),
                             dtype=LOCS_DTYPE)

                locs.sort(kind='mergesort', order='frame')

                img_info = {}
                img_info['Generated by'] = 'Picasso csv2hdf'
                img_info['Frames'] = int(_np.max(frames))+1
                img_info['Height'] = int(_np.ceil(_np.max(y)))
                img_info['Width'] = int(_np.ceil(_np.max(x)))

                info = []
                info.append(img_info)

                base, ext = os.path.splitext(path)
                out_path = base + '_locs.hdf5'
                save_locs(out_path, locs, info)
                print('Saved to {}.'.format(out_path))
            except Exception as e:
                print(e)
                print('Error. Datatype not understood.')


def _hdf2csv(path):
    from glob import glob
    import pandas as pd
    from tqdm import tqdm as _tqdm
    from os.path import isdir
    if isdir(path):
        paths = glob(path+'/*.hdf5')
    else:
        paths = glob(path)
    if paths:
        from .io import load_filter
        import os.path
        import numpy as _np
        from numpy import savetxt
        for path in _tqdm(paths):
            base, ext = os.path.splitext(path)
            if ext == '.hdf5':
                print('Converting {}'.format(path))
                out_path = base + '.csv'
                locs = pd.read_hdf(path)
                print('A total of {} rows loaded'.format(len(locs)))
                locs.to_csv(out_path, sep=',', encoding='utf-8')
    print('Complete.')


def _link(files, d_max, tolerance):
    import numpy as _np
    from tqdm import tqdm as _tqdm
    from . import lib as _lib
    from h5py import File

    import glob
    paths = glob.glob(files)
    if paths:
        from . import io, postprocess
        for path in paths:
            try:
                locs, info = io.load_locs(path)
            except io.NoMetadataFileError:
                continue
            linked_locs = postprocess.link(locs, info, d_max, tolerance)
            base, ext = os.path.splitext(path)
            link_info = {'Maximum Distance': d_max,
                         'Maximum Transient Dark Time': tolerance,
                         'Generated by': 'Picasso Link'}
            info.append(link_info)
            io.save_locs(base + '_link.hdf5', linked_locs, info)

            try:
                # Check if there is a _clusters.hdf5 file present, if yes update this file
                cluster_path = base[:-7] + '_clusters.hdf5'
                print(cluster_path)
                clusters = io.load_clusters(cluster_path)
                print('Clusterfile detected. Updating entries.')

                n_after_link = []
                linked_len = []
                linked_n = []
                linked_photonrate = []

                for group in _tqdm(_np.unique(clusters['groups'])):
                    temp = linked_locs[linked_locs['group'] == group]
                    if len(temp) > 0:
                        n_after_link.append(len(temp))
                        linked_len.append(_np.mean(temp['len']))
                        linked_n.append(_np.mean(temp['n']))
                        linked_photonrate.append(_np.mean(temp['photon_rate']))

                clusters = _lib.append_to_rec(clusters, _np.array(n_after_link, dtype=_np.int32), 'n_after_link')
                clusters = _lib.append_to_rec(clusters, _np.array(linked_len, dtype=_np.int32), 'linked_len')
                clusters = _lib.append_to_rec(clusters, _np.array(linked_n, dtype=_np.int32), 'linked_n')
                clusters = _lib.append_to_rec(clusters, _np.array(linked_photonrate, dtype=_np.float32), 'linked_photonrate')
                with File(cluster_path, 'w') as clusters_file:
                    clusters_file.create_dataset('clusters', data=clusters)
            except Exception as e:
                print(e)
                continue


def _cluster_combine(files):
    import glob
    paths = glob.glob(files)
    if paths:
        from . import io, postprocess
        for path in paths:
            try:
                locs, info = io.load_locs(path)
            except io.NoMetadataFileError:
                continue
            combined_locs = postprocess.cluster_combine(locs)
            base, ext = os.path.splitext(path)
            combined_info = {'Generated by': 'Picasso Combine'}
            info.append(combined_info)
            io.save_locs(base + '_comb.hdf5', combined_locs, info)


def _cluster_combine_dist(files):
    import glob
    paths = glob.glob(files)
    if paths:
        from . import io, postprocess
        for path in paths:
            try:
                locs, info = io.load_locs(path)
            except io.NoMetadataFileError:
                continue
            combinedist_locs = postprocess.cluster_combine_dist(locs)
            base, ext = os.path.splitext(path)
            cluster_combine_dist_info = {'Generated by': 'Picasso Combineidst'}
            info.append(cluster_combine_dist_info)
            io.save_locs(base + '_cdist.hdf5', combinedist_locs, info)


def _clusterfilter(files, clusterfile, parameter, minval, maxval):
    from glob import glob
    from itertools import chain
    from .io import load_locs, save_locs
    from .postprocess import align
    from os.path import splitext
    from tqdm import tqdm
    import numpy as np

    paths = glob(files)
    if paths:
        from . import io, postprocess
        for path in paths:
            try:
                locs, info = io.load_locs(path)
            except io.NoMetadataFileError:
                continue

            clusters = io.load_clusters(clusterfile)
            try:
                selector = (clusters[parameter] > minval) & (clusters[parameter] < maxval)
                if np.sum(selector) == 0:
                    print('Error: No localizations in range. Filtering aborted.')
                elif np.sum(selector) == len(selector):
                    print('Error: All localizations in range. Filtering aborted.')
                else:
                    print('Isolating locs.. Step 1: in range')
                    groups = clusters['groups'][selector]
                    first = True
                    for group in tqdm(groups):
                        if first:
                            all_locs = locs[locs['group'] == group]
                            first = False
                        else:
                            all_locs = np.append(all_locs, locs[locs['group'] == group])

                    base, ext = os.path.splitext(path)
                    clusterfilter_info = {'Generated by': 'Picasso Clusterfilter - in', 'Paramter': parameter, 'Minval': minval, 'Maxval': maxval}
                    info.append(clusterfilter_info)
                    all_locs.sort(kind='mergesort', order='frame')
                    all_locs = all_locs.view(np.recarray)
                    out_path =  base + '_filter_in.hdf5'
                    io.save_locs(out_path, all_locs, info)
                    print('Complete. Saved to: {}'.format(out_path))

                    print('Isolating locs.. Step 2: out of range')
                    groups = clusters['groups'][~selector]
                    first = True
                    for group in tqdm(groups):
                        if first:
                            all_locs =  locs[locs['group'] == group]
                            first = False
                        else:
                            all_locs = np.append(all_locs, locs[locs['group'] == group])

                    base, ext = os.path.splitext(path)
                    clusterfilter_info = {'Generated by': 'Picasso Clusterfilter - out', 'Paramter': parameter, 'Minval': minval, 'Maxval': maxval}
                    info.append(clusterfilter_info)
                    all_locs.sort(kind='mergesort', order='frame')
                    all_locs = all_locs.view(np.recarray)
                    out_path = base + '_filter_out.hdf5'
                    io.save_locs(out_path, all_locs, info)
                    print('Complete. Saved to: {}'.format(out_path))

            except ValueError:
                print('Error: Field {} not found.'.format(parameter))


def _undrift(files, segmentation, display=True, fromfile=None):
    import glob
    from . import io, postprocess
    from numpy import genfromtxt, savetxt
    paths = glob.glob(files)
    undrift_info = {'Generated by': 'Picasso Undrift'}
    if fromfile is not None:
        undrift_info['From File'] = fromfile
        drift = genfromtxt(fromfile)
    else:
        undrift_info['Segmentation'] = segmentation
    for path in paths:
        try:
            locs, info = io.load_locs(path)
        except io.NoMetadataFileError:
            continue
        info.append(undrift_info)
        if fromfile is not None:
            # this works for mingjies drift files but not for the own ones
            locs.x -= drift[:, 1][locs.frame]
            locs.y -= drift[:, 0][locs.frame]
            if display:
                import matplotlib.pyplot as plt
                plt.style.use('ggplot')
                plt.figure(figsize=(17, 6))
                plt.suptitle('Estimated drift')
                plt.subplot(1, 2, 1)
                plt.plot(drift[:, 1], label='x')
                plt.plot(drift[:, 0], label='y')
                plt.legend(loc='best')
                plt.xlabel('Frame')
                plt.ylabel('Drift (pixel)')
                plt.subplot(1, 2, 2)
                plt.plot(drift[:, 1], drift[:, 0], color=list(plt.rcParams['axes.prop_cycle'])[2]['color'])
                plt.axis('equal')
                plt.xlabel('x')
                plt.ylabel('y')
                plt.show()
        else:
            print('Undrifting file {}'.format(path))
            drift, locs = postprocess.undrift(locs, info, segmentation, display=display)
        base, ext = os.path.splitext(path)
        io.save_locs(base + '_undrift.hdf5', locs, info)
        savetxt(base + '_drift.txt', drift, header='dx\tdy', newline='\r\n')


def _density(files, radius):
    import glob
    paths = glob.glob(files)
    if paths:
        from . import io, postprocess
        for path in paths:
            locs, info = io.load_locs(path)
            locs = postprocess.compute_local_density(locs, info, radius)
            base, ext = os.path.splitext(path)
            density_info = {'Generated by': 'Picasso Density',
                            'Radius': radius}
            info.append(density_info)
            io.save_locs(base + '_density.hdf5', locs, info)


def _dbscan(files, radius, min_density):
    import glob
    paths = glob.glob(files)
    if paths:
        from . import io, postprocess
        from h5py import File
        for path in paths:
            print('Loading {} ...'.format(path))
            locs, info = io.load_locs(path)
            clusters, locs = postprocess.dbscan(locs, radius, min_density)
            base, ext = os.path.splitext(path)
            dbscan_info = {'Generated by': 'Picasso DBSCAN',
                           'Radius': radius,
                           'Minimum local density': min_density}
            info.append(dbscan_info)
            io.save_locs(base + '_dbscan.hdf5', locs, info)
            with File(base + '_dbclusters.hdf5', 'w') as clusters_file:
                clusters_file.create_dataset('clusters', data=clusters)


def _nneighbor(files):
    import glob
    import h5py as _h5py
    import numpy as np
    from scipy.spatial import distance
    paths = glob.glob(files)
    if paths:
        from . import io, postprocess
        from h5py import File
        for path in paths:
            print('Loading {} ...'.format(path))
            with _h5py.File(path, 'r') as locs_file:
                locs = locs_file['clusters'][...]
            clusters = np.rec.array(locs, dtype=locs.dtype)
            points = np.array(clusters[['com_x', 'com_y']].tolist())
            alldist = distance.cdist(points, points)
            alldist[alldist == 0] = float('inf')
            minvals = np.amin(alldist, axis=0)
            base, ext = os.path.splitext(path)
            out_path = base + '_minval.txt'
            np.savetxt(out_path, minvals, newline='\r\n')
            print('Saved filest o: {}'.format(out_path))


def _dark(files):
    import glob
    paths = glob.glob(files)
    if paths:
        from . import io, postprocess
        for path in paths:
            locs, info = io.load_locs(path)
            locs = postprocess.compute_dark_times(locs)
            base, ext = os.path.splitext(path)
            dbscan_info = {'Generated by': 'Picasso Dark'}
            info.append(dbscan_info)
            io.save_locs(base + '_dark.hdf5', locs, info)


def _align(files, display):
    from glob import glob
    from itertools import chain
    from .io import load_locs, save_locs
    from .postprocess import align
    from os.path import splitext
    files = list(chain(*[glob(_) for _ in files]))
    print('Aligning files:')
    for f in files:
        print('  ' + f)
    locs_infos = [load_locs(_) for _ in files]
    locs = [_[0] for _ in locs_infos]
    infos = [_[1] for _ in locs_infos]
    aligned_locs = align(locs, infos, display=display)
    align_info = {'Generated by': 'Picasso Align',
                  'Files': files}
    for file, locs_, info in zip(files, aligned_locs, infos):
        info.append(align_info)
        base, ext = splitext(file)
        save_locs(base + '_align.hdf5', locs_, info)


def _join(files):
    from .io import load_locs, save_locs
    from os.path import splitext
    from numpy import append
    import numpy as np
    locs, info = load_locs(files[0])
    join_info = {'Generated by': 'Picasso Join',
                 'Files': [files[0]]}
    for path in files[1:]:
        locs_, info_ = load_locs(path)
        locs = append(locs, locs_)
        join_info['Files'].append(path)
    base, ext = splitext(files[0])
    info.append(join_info)
    locs.sort(kind='mergesort', order='frame')
    locs = locs.view(np.recarray)
    save_locs(base + '_join.hdf5', locs, info)


def _groupprops(files):
    import glob
    paths = glob.glob(files)
    if paths:
        from .io import load_locs, save_datasets
        from .postprocess import groupprops
        from os.path import splitext
        for path in paths:
            locs, info = load_locs(path)
            groups = groupprops(locs)
            base, ext = splitext(path)
            save_datasets(base + '_groupprops.hdf5', info, locs=locs, groups=groups)


def _pair_correlation(files, bin_size, r_max):
    from glob import glob
    paths = glob(files)
    if paths:
        from .io import load_locs
        from .postprocess import pair_correlation
        from matplotlib.pyplot import plot, style, show, xlabel, ylabel, title
        style.use('ggplot')
        for path in paths:
            print('Loading {}...'.format(path))
            locs, info = load_locs(path)
            print('Calculating pair-correlation...')
            bins_lower, pc = pair_correlation(locs, info, bin_size, r_max)
            plot(bins_lower-bin_size/2, pc)
            xlabel('r (pixel)')
            ylabel('pair-correlation (pixel^-2)')
            title('Pair-correlation. Bin size: {}, R max: {}'.format(bin_size, r_max))
            show()


def _localize(args):
    files = args.files
    from glob import glob
    from .io import load_movie, save_locs
    from .localize import get_spots, identify_async, identifications_from_futures, fit_async, locs_from_fits
    from os.path import splitext, isdir
    from time import sleep
    from . import gausslq, gaussmle, avgroi, lib
    import os.path as _ospath
    import re as _re
    import os as _os

    print('    ____  _____________   __________ ____ ')
    print('   / __ \\/  _/ ____/   | / ___/ ___// __ \\')
    print('  / /_/ // // /   / /| | \\__ \\\\__ \\/ / / /')
    print(' / _____/ // /___/ ___ |___/ ___/ / /_/ / ')
    print('/_/   /___/\\____/_/  |_/____/____/\\____/  ')
    print('                                          ')
    print('------------------------------------------')
    print('Localize - Parameters:')
    print('{:<8} {:<15} {:<10}'.format('No', 'Label', 'Value'))

    if args.fit_method == 'lq-gpu':
        if gausslq.gpufit_installed:
            print('GPUfit installed')
        else:
            raise Exception('GPUfit not installed. Aborting.')

    for index, element in enumerate(vars(args)):
        print('{:<8} {:<15} {:<10}'.format(index+1, element, getattr(args, element)))
    print('------------------------------------------')

    def check_consecutive_tif(filepath):
        """
        Function to only return the first file of a consecutive ome.tif series to not reconstruct all of them
        as load_movie automatically detects consecutive files.
        e.g. have a folder with file.ome.tif, file_1.ome.tif, file_2.ome.tif, will return only file.ome.tif
        """
        files = glob(filepath+'/*.tif')
        newlist = [_ospath.abspath(file) for file in files]
        for file in files:
            path = _ospath.abspath(file)
            directory = _ospath.dirname(path)
            base, ext = _ospath.splitext(_ospath.splitext(path)[0])    # split two extensions as in .ome.tif
            base = _re.escape(base)
            pattern = _re.compile(base + '_(\d*).ome.tif')    # This matches the basename + an appendix of the file number
            entries = [_.path for _ in _os.scandir(directory) if _.is_file()]
            matches = [_re.match(pattern, _) for _ in entries]
            matches = [_ for _ in matches if _ is not None]
            paths_indices = [(int(_.group(1)), _.group(0)) for _ in matches]
            datafiles = [_.group(0) for _ in matches]
            if datafiles != []:
                for element in datafiles:
                    newlist.remove(element)
        return newlist

    if isdir(files):
        print('Analyzing folder')

        tif_files = check_consecutive_tif(files)

        paths = tif_files+glob(files+'*.raw')
        print('A total of {} files detected'.format(len(paths)))
    else:
        paths = glob(files)

    if paths:
        def prompt_info():
            info = {}
            info['Byte Order'] = input('Byte Order (< or >): ')
            info['Data Type'] = input('Data Type (e.g. "uint16"): ')
            info['Frames'] = int(input('Frames: '))
            info['Height'] = int(input('Height: '))
            info['Width'] = int(input('Width: '))
            save = input('Save info to yaml file (y/n): ') == 'y'
            return info, save

        box = args.box_side_length
        min_net_gradient = args.gradient
        camera_info = {}
        camera_info['baseline'] = args.baseline
        camera_info['sensitivity'] = args.sensitivity
        camera_info['gain'] = args.gain
        camera_info['qe'] = args.qe

        if args.fit_method == 'mle':
            # use default settings
            convergence = 0.001
            max_iterations = 1000
        else:
            convergence = 0
            max_iterations = 0

        for path in paths:
            print('------------------------------------------')
            print('------------------------------------------')
            print('Processing {}'.format(path))
            print('------------------------------------------')
            movie, info = load_movie(path)
            current, futures = identify_async(movie, min_net_gradient, box)
            n_frames = len(movie)
            while current[0] < n_frames:
                print('Identifying in frame {:,} of {:,}'.format(current[0]+1, n_frames), end='\r')
                sleep(0.2)
            print('Identifying in frame {:,} of {:,}'.format(n_frames, n_frames))
            ids = identifications_from_futures(futures)

            if args.fit_method == 'lq':
                spots = get_spots(movie, ids, box, camera_info)
                theta = gausslq.fit_spots_parallel(spots, async=False)
                locs = gausslq.locs_from_fits(ids, theta, box, args.gain)
            elif args.fit_method == 'lq-gpu':
                spots = get_spots(movie, ids, box, camera_info)
                theta = gausslq.fit_spots_gpufit(spots)
                em = camera_info['gain'] > 1
                locs = gausslq.locs_from_fits_gpufit(ids, theta, box, em)
            elif args.fit_method == 'mle':
                current, thetas, CRLBs, likelihoods, iterations = fit_async(movie,
                                                                        camera_info,
                                                                        ids,
                                                                        box,
                                                                        convergence,
                                                                        max_iterations)
                n_spots = len(ids)
                while current[0] < n_spots:
                    print('Fitting spot {:,} of {:,}'.format(current[0]+1, n_spots), end='\r')
                    sleep(0.2)
                print('Fitting spot {:,} of {:,}'.format(n_spots, n_spots))
                locs = locs_from_fits(ids, thetas, CRLBs, likelihoods, iterations, box)

            elif args.fit_method == 'avg':
                spots = get_spots(movie, ids, box, camera_info)
                theta = avgroi.fit_spots_parallel(spots, async=False)
                locs = avgroi.locs_from_fits(ids, theta, box, args.gain)

            else:
                print('This should never happen...')

            localize_info = {'Generated by': 'Picasso Localize',
                             'ROI': None,
                             'Box Size': box,
                             'Min. Net Gradient': min_net_gradient,
                             'Convergence Criterion': convergence,
                             'Max. Iterations': max_iterations}
            info.append(localize_info)
            base, ext = splitext(path)
            out_path = base + '_locs.hdf5'
            save_locs(out_path, locs, info)
            print('File saved to {}'.format(out_path))
            if args.drift > 0:
                print('Undrifting file:')
                print('------------------------------------------')
                try:
                    _undrift(out_path, args.drift, display=False, fromfile=None)
                except Exception as e:
                    print(e)
                    print('Drift correction failed for {}'.format(out_path))

            print('                                          ')
    else:
        print('Error. No files found.')


def _render(args):
    from .lib import locs_glob_map
    from .render import render
    from os.path import splitext
    from matplotlib.pyplot import imsave
    from os import startfile
    from .io import load_user_settings, save_user_settings

    def render_many(locs, info, path, oversampling, blur_method, min_blur_width, vmin, vmax, cmap, silent):
        if blur_method == 'none':
            blur_method = None
        N, image = render(locs, info, oversampling, blur_method=blur_method, min_blur_width=min_blur_width)
        base, ext = splitext(path)
        out_path = base + '.png'
        im_max = image.max() / 100
        imsave(out_path, image, vmin=vmin * im_max, vmax=vmax * im_max, cmap=cmap)
        if not silent:
            startfile(out_path)

    settings = load_user_settings()
    cmap = args.cmap
    if cmap is None:
        try:
            cmap = settings['Render']['Colormap']
        except KeyError:
            cmap = 'viridis'
    settings['Render']['Colormap'] = cmap
    save_user_settings(settings)

    locs_glob_map(render_many, args.files, args=(args.oversampling, args.blur_method, args.min_blur_width, args.vmin, args.vmax,
                                                 cmap, args.silent))


def main():
    import argparse

    # Main parser
    parser = argparse.ArgumentParser('picasso')
    subparsers = parser.add_subparsers(dest='command')

    for command in ['toraw', 'localize', 'filter', 'render']:
        subparsers.add_parser(command)

    # link parser
    link_parser = subparsers.add_parser('link', help='link localizations in consecutive frames')
    link_parser.add_argument('files', help='one or multiple hdf5 localization files specified by a unix style path pattern')
    link_parser.add_argument('-d', '--distance', type=float, default=1.0,
                             help='maximum distance between localizations to consider them the same binding event (default=1.0)')
    link_parser.add_argument('-t', '--tolerance', type=int, default=1,
                             help='maximum dark time between localizations to still consider them the same binding event (default=1)')

    cluster_combine_parser = subparsers.add_parser('cluster_combine', help='combine localization in each cluster of a group')
    cluster_combine_parser.add_argument('files', help='one or multiple hdf5 localization files specified by a unix style path pattern')

    cluster_combine_dist_parser = subparsers.add_parser('cluster_combine_dist', help='calculate the nearest neighbor for each combined cluster')
    cluster_combine_dist_parser.add_argument('files', help='one or multiple hdf5 localization files specified by a unix style path pattern')

    clusterfilter_parser = subparsers.add_parser('clusterfilter', help='filter localizations by properties of their clusters')
    clusterfilter_parser.add_argument('files', help='one or multiple hdf5 localization files specified by a unix style path pattern')
    clusterfilter_parser.add_argument('clusterfile', help='a hdf5 clusterfile')
    clusterfilter_parser.add_argument('parameter', type=str, help='parameter to be filtered')
    clusterfilter_parser.add_argument('minval',  type=float, help='lower boundary')
    clusterfilter_parser.add_argument('maxval', type=float, help='upper boundary')

    # undrift parser
    undrift_parser = subparsers.add_parser('undrift', help='correct localization coordinates for drift')
    undrift_parser.add_argument('files', help='one or multiple hdf5 localization files specified by a unix style path pattern')
    undrift_parser.add_argument('-m', '--mode', default='render', help='"std", "render" or "framepair")')
    undrift_parser.add_argument('-s', '--segmentation', type=float, default=1000,
                                help='the number of frames to be combined for one temporal segment (default=1000)')
    undrift_parser.add_argument('-f', '--fromfile', type=str, help='apply drift from specified file instead of computing it')
    undrift_parser.add_argument('-d', '--nodisplay', action='store_false', help='do not display estimated drift')

    # local densitydd
    density_parser = subparsers.add_parser('density', help='compute the local density of localizations')
    density_parser.add_argument('files', help='one or multiple hdf5 localization files specified by a unix style path pattern')
    density_parser.add_argument('radius', type=float, help='maximal distance between to localizations to be considered local')

    # DBSCAN
    dbscan_parser = subparsers.add_parser('dbscan', help='cluster localizations with the dbscan clustering algorithm')
    dbscan_parser.add_argument('files', help='one or multiple hdf5 localization files specified by a unix style path pattern')
    dbscan_parser.add_argument('radius', type=float, help='maximal distance between to localizations to be considered local')
    dbscan_parser.add_argument('density', type=int, help='minimum local density for localizations to be assigned to a cluster')

    # Dark time
    dark_parser = subparsers.add_parser('dark', help='compute the dark time for grouped localizations')
    dark_parser.add_argument('files', help='one or multiple hdf5 localization files specified by a unix style path pattern')

    # align
    align_parser = subparsers.add_parser('align', help='align one localization file to another')
    align_parser.add_argument('-d', '--display', help='display correlation', action='store_true')
    # align_parser.add_argument('-a', '--affine', help='include affine transformations (may take long time)', action='store_true')
    align_parser.add_argument('file', help='one or multiple hdf5 localization files', nargs='+')

    # join
    join_parser = subparsers.add_parser('join', help='join hdf5 localization lists')
    join_parser.add_argument('file', nargs='+', help='the hdf5 localization files to be joined')

    # group properties
    groupprops_parser = subparsers.add_parser('groupprops', help='calculate and various properties of localization groups')
    groupprops_parser.add_argument('files', help='one or multiple hdf5 localization files specified by a unix style path pattern')

    # Pair correlation
    pc_parser = subparsers.add_parser('pc', help='calculate the pair-correlation of localizations')
    pc_parser.add_argument('-b', '--binsize', type=float, default=0.1, help='the bin size')
    pc_parser.add_argument('-r', '--rmax', type=float, default=10, help='The maximum distance to calculate the pair-correlation')
    pc_parser.add_argument('files', help='one or multiple hdf5 localization files specified by a unix style path pattern')

    # localize
    localize_parser = subparsers.add_parser('localize', help='identify and fit single molecule spots')
    localize_parser.add_argument('files', nargs='?', help='one movie file or a folder containing movie files specified by a unix style path pattern')
    localize_parser.add_argument('-b', '--box-side-length', type=int, default=7, help='box side length')
    localize_parser.add_argument('-a', '--fit-method', choices=['mle', 'lq', 'lq-gpu', 'avg'], default='mle')
    localize_parser.add_argument('-g', '--gradient', type=int, default=5000, help='minimum net gradient')
    localize_parser.add_argument('-d', '--drift', type=int, default=1000, help='segmentation size for subsequent RCC, 0 to deactivate')
    localize_parser.add_argument('-bl', '--baseline', type=int, default=0, help='camera baseline')
    localize_parser.add_argument('-s', '--sensitivity', type=int, default=1, help='camera sensitivity')
    localize_parser.add_argument('-ga', '--gain', type=int, default=1, help='camera gain')
    localize_parser.add_argument('-qe', '--qe', type=int, default=1, help='camera quantum efficiency')

    # nneighbors
    nneighbor_parser = subparsers.add_parser('nneighbor', help='calculate nearest neighbor of a clustered dataset')
    nneighbor_parser.add_argument('files', nargs='?', help='one or multiple hdf5 clustered files specified by a unix style path pattern')

    # render
    render_parser = subparsers.add_parser('render', help='render localization based images')
    render_parser.add_argument('files', nargs='?', help='one or multiple localization files specified by a unix style path pattern')
    render_parser.add_argument('-o', '--oversampling', type=float, default=1.0, help='the number of super-resolution pixels per camera pixels')
    render_parser.add_argument('-b', '--blur-method', choices=['none', 'convolve', 'gaussian'], default='convolve')
    render_parser.add_argument('-w', '--min-blur-width', type=float, default=0.0, help='minimum blur width if blur is applied')
    render_parser.add_argument('--vmin', type=float, default=0.0, help='minimum colormap level in range 0-100')
    render_parser.add_argument('--vmax', type=float, default=20.0, help='maximum colormap level in range 0-100')
    render_parser.add_argument('-c', '--cmap', choices=['viridis', 'inferno', 'plasma', 'magma', 'hot', 'gray'], help='the colormap to be applied')
    render_parser.add_argument('-s', '--silent', action='store_true', help='do not open the image file')

    # design
    subparsers.add_parser('design', help='design RRO DNA origami structures')
    # simulate
    subparsers.add_parser('simulate', help='simulate single molecule fluorescence data')

    # average
    average_parser = subparsers.add_parser('average', help='particle averaging')
    average_parser.add_argument('-o', '--oversampling', type=float, default=10,
                                help='oversampling of the super-resolution images for alignment evaluation')
    average_parser.add_argument('-i', '--iterations', type=int, default=20)
    average_parser.add_argument('files', nargs='?', help='a localization file with grouped localizations')

    average3_parser = subparsers.add_parser('average3', help='three-dimensional particle averaging')

    hdf2visp_parser = subparsers.add_parser('hdf2visp')
    hdf2visp_parser.add_argument('files')
    hdf2visp_parser.add_argument('pixelsize', type=float)

    csv2hdf_parser = subparsers.add_parser('csv2hdf')
    csv2hdf_parser.add_argument('files')
    csv2hdf_parser.add_argument('pixelsize', type=float)

    hdf2csv_parser = subparsers.add_parser('hdf2csv')
    hdf2csv_parser.add_argument('files')

    # Parse
    args = parser.parse_args()
    if args.command:
        if args.command == 'toraw':
            from .gui import toraw
            toraw.main()
        elif args.command == 'localize':
            if args.files:
                _localize(args)
            else:
                from picasso.gui import localize
                localize.main()
        elif args.command == 'filter':
            from .gui import filter
            filter.main()
        elif args.command == 'render':
            if args.files:
                _render(args)
            else:
                from .gui import render
                render.main()
        elif args.command == 'average':
            if args.files:
                _average(args)
            else:
                from .gui import average
                average.main()
        elif args.command == 'average3':
                from .gui import average3
                average3.main()
        elif args.command == 'link':
            _link(args.files, args.distance, args.tolerance)
        elif args.command == 'cluster_combine':
            _cluster_combine(args.files)
        elif args.command == 'cluster_combine_dist':
            _cluster_combine_dist(args.files)
        elif args.command == 'clusterfilter':
            _clusterfilter(args.files, args.clusterfile, args.parameter, args.minval, args.maxval)
        elif args.command == 'undrift':
            _undrift(args.files, args.segmentation, args.nodisplay, args.fromfile)
        elif args.command == 'density':
            _density(args.files, args.radius)
        elif args.command == 'dbscan':
            _dbscan(args.files, args.radius, args.density)
        elif args.command == 'nneighbor':
            _nneighbor(args.files)
        elif args.command == 'dark':
            _dark(args.files)
        elif args.command == 'align':
            _align(args.file, args.display)
        elif args.command == 'join':
            _join(args.file)
        elif args.command == 'groupprops':
            _groupprops(args.files)
        elif args.command == 'pc':
            _pair_correlation(args.files, args.binsize, args.rmax)
        elif args.command == 'simulate':
            from .gui import simulate
            simulate.main()
        elif args.command == 'design':
            from .gui import design
            design.main()
        elif args.command == 'hdf2visp':
            _hdf2visp(args.files, args.pixelsize)
        elif args.command == 'csv2hdf':
            _csv2hdf(args.files, args.pixelsize)
        elif args.command == 'hdf2csv':
            _hdf2csv(args.files)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
