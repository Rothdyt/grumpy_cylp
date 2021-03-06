# -*- coding: utf-8 -*-
"""
Created on Thu May 14 02:03:56 2020

@author: Muqing Zheng
"""

import numpy as np
import math,sys,os
from random import seed
from random import randint
import matplotlib.pyplot as plt
import pandas as pd

from coinor.grumpy import GenerateRandomMIP
from coinor.grumpy import BBTree
from coinor.grumpy import MOST_FRACTIONAL, FIXED_BRANCHING, PSEUDOCOST_BRANCHING
from coinor.grumpy import DEPTH_FIRST, BEST_FIRST, BEST_ESTIMATE
from coinor.grumpy import INFINITY

project_dir = '../'
sys.path.append(project_dir)

from src.cylpBranchAndBound import RELIABILITY_BRANCHING, HYBRID
from src.cylpBranchAndBound import BranchAndBound

# Disable
def blockPrint():
    sys.stdout = open(os.devnull, 'w')

# Restore
def enablePrint():
    sys.stdout = sys.__stdout__
    
    
def identity(n):
    m=[[0 for x in range(n)] for y in range(n)]
    for i in range(0,n):
        m[i][i] = 1
    return m

def negIdentity(n):
    m=[[0 for x in range(n)] for y in range(n)]
    for i in range(0,n):
        m[i][i] = -1
    return m



# input Parameters 
M = 30  # Number of Problems
seed(1020)



##################################################
#branch= [MOST_FRACTIONAL, FIXED_BRANCHING, PSEUDOCOST_BRANCHING,RELIABILITY_BRANCHING,HYBRID]
branch= [PSEUDOCOST_BRANCHING,RELIABILITY_BRANCHING,HYBRID]
search = [DEPTH_FIRST, BEST_FIRST, BEST_ESTIMATE]
prob_data = np.array([]) # Record type of problems
costs_node = {i + ' - ' + j:np.array([]) for i in branch for j in search}
costs_time = {i + ' - ' + j:np.array([]) for i in branch for j in search}
costs_lp = {i + ' - ' + j:np.array([]) for i in branch for j in search}

# Solve problems and record tree size of costs
for k in range(M):
    # Problem Size will be random
    numVars = randint(5,25)
    numCons = randint(int(numVars/5),int(2 * numVars/3))
    rand_seed = randint(1,2000)
    #prob_data = np.append(prob_data,(numVars,numCons,rand_seed))
    CONSTRAINTS, VARIABLES, OBJ, MAT, RHS = GenerateRandomMIP(
        numVars=numVars , numCons=numCons,rand_seed= rand_seed)
    
    I = identity(len(VARIABLES))
    negI = negIdentity(len(VARIABLES))
    RHS = RHS + [0]*len(VARIABLES) + [3]*len(VARIABLES)
    for i in VARIABLES:
        MAT[i] = MAT[i] + negI[int(i[1:])]
        CONSTRAINTS.append('C'+str(len(CONSTRAINTS)))
    for i in VARIABLES:
        MAT[i] = MAT[i] + I[int(i[1:])]
        CONSTRAINTS.append('C'+str(len(CONSTRAINTS)))
        
    for i in branch:
        for j in search:
            T = BBTree()
            opt, LB,stat = BranchAndBound(
                T, CONSTRAINTS, VARIABLES, OBJ,MAT, RHS,branch_strategy=i,search_strategy=j,
                more_return = True,binary_vars = False)
            if LB>-INFINITY:
                costs_node[i + ' - ' + j] = np.append(costs_node[i + ' - ' + j],int(stat['Size']))
                costs_time[i + ' - ' + j] = np.append(costs_time[i + ' - ' + j],float(stat['Time']))
                costs_lp[i + ' - ' + j] = np.append(costs_lp[i + ' - ' + j],int(stat['LP Solved']))
            else:
                costs_node[i + ' - ' + j] = np.append(costs_node[i + ' - ' + j],INFINITY)
                costs_time[i + ' - ' + j] = np.append(costs_time[i + ' - ' + j],INFINITY)
                costs_lp[i + ' - ' + j] = np.append(costs_lp[i + ' - ' + j],INFINITY)
                
                
def performance_profile(costs,name):
    # Do some computations
    # Calculate Minimum Cost of Each Problem
    min_costs = np.ones(M)*math.inf
    for i in branch:
        for j in search:
            for k in range(M):
                 if costs[i + ' - ' + j][k]<min_costs[k]:
                    min_costs[k] = costs[i + ' - ' + j][k]

    # Calculate Ratio of Each Problem  with Each Method              
    ratios = costs
    for i in branch:
        for j in search:
            for k in range(M):
                ratios[i + ' - ' + j][k] = costs[i + ' - ' + j][k]/min_costs[k]

    # Efficients
    effs = np.zeros(len(branch) * len(search))
    ind = 0
    for rk in ratios.keys():
        effs[ind] = np.sum(ratios[rk]<=1)/M
        ind += 1

    # Robustness    
    rmax = 0
    for rk in ratios.keys():
        if np.max(ratios[rk]) >rmax:
            rmax = np.max(ratios[rk])

    robs = np.zeros(len(branch) * len(search))
    ind = 0
    for rk in ratios.keys():
        robs[ind] = np.sum(ratios[rk]<=rmax)/M
        ind += 1

    # Print a table
    d = {'Method':list(ratios.keys()),'Efficiency':effs,'Robustness':robs}
    df = pd.DataFrame(data=d)
    with open(name + '.tex', 'w') as tf:
         tf.write(df.to_latex(index=False))
            
    # Do plot
    all_rs = np.array([])
    for rk in ratios.keys():
        all_rs = np.append(all_rs,ratios[rk])

    # x-axis
    t = np.sort(np.unique(all_rs))
    # for rk in ratios.keys():
    #     plt.plot(t,[np.sum(ratios[rk]<=t[i])/M for i in range(len(t)) ],label = rk)

    # plt.xlabel('Performance Ratio')
    # plt.ylabel('Percents of Problem Solved')
    # plt.legend(bbox_to_anchor=(1.05, 1.0), loc='upper left')
    # plt.savefig(name + ' ' + 'Performance_Profile_All')
    # plt.show()
    
    for i in branch:
        count = 0
        for rk in ratios.keys():
            if i in rk:
                if count == 0:
                    plt.plot(t,[np.sum(ratios[rk]<=t[i])/M for i in range(len(t)) ],'*-',label = rk)
                    count += 1
                else:
                    plt.plot(t,[np.sum(ratios[rk]<=t[i])/M for i in range(len(t)) ],label = rk)
        plt.xlabel('Performance Ratio')
        plt.ylabel('Percents of Problem Solved')
        plt.legend( loc='lower right')
        plt.savefig(name + ' ' + i)
        plt.show()

    for j in search:
        count = 0
        for rk in ratios.keys():
            if j in rk:
                if count == 0:
                    plt.plot(t,[np.sum(ratios[rk]<=t[i])/M for i in range(len(t)) ],'*-',label = rk)
                    count += 1
                else:
                    plt.plot(t,[np.sum(ratios[rk]<=t[i])/M for i in range(len(t)) ],label = rk)
        plt.xlabel('Performance Ratio')
        plt.ylabel('Percents of Problem Solved')
        plt.legend(loc='lower right')
        plt.savefig(name + ' ' + j)
        plt.show()
        
        
        
if __name__ == '__main__':
    enablePrint()
    performance_profile(costs_node, 'Tree Size')
    performance_profile(costs_time, 'Solution Time')
    performance_profile(costs_lp, 'LP Solved')