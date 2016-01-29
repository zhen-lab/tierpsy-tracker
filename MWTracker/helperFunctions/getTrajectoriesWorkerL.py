# -*- coding: utf-8 -*-
"""
Created on Fri Apr  3 01:56:06 2015

@author: ajaver
"""
import os, sys
import tables

from .. import config_param

from ..trackWorms.getWormTrajectories import getWormTrajectories, joinTrajectories, correctSingleWormCase
from ..trackWorms.getDrawTrajectories import drawTrajectoriesVideo
from ..trackWorms.getSkeletonsTables import trajectories2Skeletons, writeIndividualMovies
from ..trackWorms.checkHeadOrientation import correctHeadTail

from ..featuresAnalysis.getFilteredFeats import getFilteredFeats
from ..featuresAnalysis.obtainFeatures import getWormFeaturesFilt

from ..helperFunctions.tracker_param import tracker_param


from collections import OrderedDict

#the order of the list is very important, and reflects the order where is step is done
checkpoint_label = ['TRAJ_CREATE', 'TRAJ_JOIN', 'SKE_CREATE', 'SKE_ORIENT', 'SKE_FILT', 
'FEAT_CREATE','FEAT_MANUAL_CREATE', 'END']
checkpoint = {ii:x for x,ii in enumerate(checkpoint_label)}

def print_flush(pstr):
        print(pstr)
        sys.stdout.flush()

def getStartingPoint(masked_image_file, results_dir):    
    '''determine for where to start. This is useful to check if the previous analysis was 
    completely succesfully, or if it was interrupted restarted from the last succesful step'''
    
    base_name, trajectories_file, skeletons_file, features_file, feat_ind_file = constructNames(masked_image_file, results_dir)

    try:
        with tables.open_file(trajectories_file, mode = 'r') as traj_fid:
             trajectories = traj_fid.get_node('/plate_worms')
             if trajectories._v_attrs['has_finished'] == 0:
                 return checkpoint['TRAJ_CREATE'];
             elif trajectories._v_attrs['has_finished'] == 1:
                 return checkpoint['TRAJ_JOIN'];
    except:
        #if there is any problem while reading the file, create it again
        return checkpoint['TRAJ_CREATE'];

    try:
        with tables.File(skeletons_file, "r") as ske_file_id:
            skeleton_table = ske_file_id.get_node('/skeleton')
            if skeleton_table._v_attrs['has_finished'] == 0:
                return checkpoint['SKE_CREATE'];
            elif skeleton_table._v_attrs['has_finished'] == 1:
                return checkpoint['SKE_ORIENT'];
            elif skeleton_table._v_attrs['has_finished'] == 2:
                return checkpoint['SKE_FILT'];
    except:
        #if there is any problem while reading the file, create it again
        return checkpoint['SKE_CREATE'];
    

    try:
        with tables.File(features_file, "r") as feat_file_id:
            features_table = feat_file_id.get_node('/features_means')
            if features_table._v_attrs['has_finished'] == 0:
                return checkpoint['FEAT_CREATE'];

    except:
        #if there is any problem while reading the file, create it again
        return checkpoint['FEAT_CREATE'];
    
    try:
        with tables.File(feat_ind_file, "r") as feat_file_id:
            features_table = feat_file_id.get_node('/features_means')
            if features_table._v_attrs['has_finished'] == 0:
                return checkpoint['FEAT_MANUAL_CREATE'];
    except:
        #if there is any problem while reading the file, create it again
        with tables.File(skeletons_file, 'r') as ske_file_id:
            if 'worm_label' in ske_file_id.get_node('/trajectories_data').colnames:
                return checkpoint['FEAT_MANUAL_CREATE'];

        
    return checkpoint['END'];


def constructNames(masked_image_file, results_dir):
    base_name = masked_image_file.rpartition('.')[0].rpartition(os.sep)[-1]

    output = [base_name]
    
    ext2add = ['trajectories', 'skeletons', 'features', 'feat_manual']
    for ext in ext2add:
        output += [os.path.abspath(os.path.join(results_dir, base_name + '_' + ext + '.hdf5'))]
    
    return output

def getTrajectoriesWorkerL(masked_image_file, results_dir, param_file ='', overwrite = False, 
    start_point = -1, end_point = checkpoint['END'], is_single_worm = False, 
    use_auto_label = True, use_manual_join = False):
    
    base_name, trajectories_file, skeletons_file, features_file, feat_manual_file = constructNames(masked_image_file, results_dir)
    print(trajectories_file, skeletons_file, features_file, feat_manual_file)

    #if starting point is not given, calculate it again
    if overwrite:
        start_point = checkpoint['TRAJ_CREATE']
    elif start_point < 0:
        start_point = getStartingPoint(masked_image_file, results_dir)

    #if start_point is larger than end_point there is nothing else to do 
    if start_point > end_point:
        print_flush(base_name + ' Finished in ' + checkpoint_label[end_point])
        return

    if start_point < checkpoint['FEAT_CREATE']:
        #check if the file with the masked images exists
        assert os.path.exists(masked_image_file)
    
    if results_dir[-1] != os.sep:
        results_dir += os.sep
    if not os.path.exists(results_dir):
        try:
            os.makedirs(results_dir)
        except:
            pass
    
    #%%
    #get function parameters
    param = tracker_param(param_file)
    
    execThisPoint = lambda current_point : (checkpoint[current_point] >= start_point ) &  (checkpoint[current_point] <= end_point)
    

    print_flush(base_name + ' Starting checkpoint: ' + checkpoint_label[start_point])
    
    #get trajectory data
    if execThisPoint('TRAJ_CREATE'):
        getWormTrajectories(masked_image_file, trajectories_file, **param.trajectories_param)
        if is_single_worm: correctSingleWormCase(trajectories_file)

    if execThisPoint('TRAJ_JOIN'):        
        joinTrajectories(trajectories_file, **param.join_traj_param)

    #get skeletons data    
    if execThisPoint('SKE_CREATE'):
        trajectories2Skeletons(masked_image_file, skeletons_file, trajectories_file, **param.skeletons_param)

    if execThisPoint('SKE_ORIENT'):
        correctHeadTail(skeletons_file, **param.head_tail_param)
    
    if is_single_worm:
        #we need to force parameters to obtain the correct features
        use_manual_join = False
        use_auto_label = False
        param.head_tail_param['min_dist'] = 0

    if execThisPoint('SKE_FILT'):
        getFilteredFeats(skeletons_file, use_auto_label, **param.feat_filt_param)
    
    #get features
    if execThisPoint('FEAT_CREATE'):
        getWormFeaturesFilt(skeletons_file, features_file, use_auto_label, False, param.feat_filt_param)
    
    if execThisPoint('FEAT_MANUAL_CREATE') and use_manual_join:
        getWormFeaturesFilt(skeletons_file, feat_manual_file, use_auto_label, True)
    
    print_flush(base_name + ' Finished')
    
    