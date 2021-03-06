# -*- coding: utf-8 -*-
"""
Created on Wed May 13 13:44:54 2020

@author: Muqing Zheng
"""

import sys
import math
import time
from coinor.blimpy import PriorityQueue
from past.utils import old_div
from coinor.grumpy import BBTree
from coinor.grumpy import MOST_FRACTIONAL, FIXED_BRANCHING, PSEUDOCOST_BRANCHING
from coinor.grumpy import DEPTH_FIRST, BEST_FIRST, BEST_ESTIMATE, INFINITY
import numpy as np
from cylp.cy.CyClpSimplex import CyClpSimplex
from cylp.py.modeling.CyLPModel import CyLPModel, CyLPArray


def BranchAndBoundCylp(T, CONSTRAINTS, VARIABLES, OBJ, MAT, RHS,
                   branch_strategy=MOST_FRACTIONAL,
                   search_strategy=DEPTH_FIRST,
                   complete_enumeration=False,
                   display_interval=None,
                   binary_vars=True):
    if T.get_layout() == 'dot2tex':
        cluster_attrs = {'name':'Key', 'label':r'\text{Key}', 'fontsize':'12'}
        T.add_node('C', label = r'\text{Candidate}', style = 'filled',
                      color = 'yellow', fillcolor = 'yellow')
        T.add_node('I', label = r'\text{Infeasible}', style = 'filled',
                      color = 'orange', fillcolor = 'orange')
        T.add_node('S', label = r'\text{Solution}', style = 'filled',
                      color = 'lightblue', fillcolor = 'lightblue')
        T.add_node('P', label = r'\text{Pruned}', style = 'filled',
                      color = 'red', fillcolor = 'red')
        T.add_node('PC', label = r'\text{Pruned}$\\ $\text{Candidate}', style = 'filled',
                      color = 'red', fillcolor = 'yellow')
    else:
        cluster_attrs = {'name':'Key', 'label':'Key', 'fontsize':'12'}
        T.add_node('C', label = 'Candidate', style = 'filled',
                      color = 'yellow', fillcolor = 'yellow')
        T.add_node('I', label = 'Infeasible', style = 'filled',
                      color = 'orange', fillcolor = 'orange')
        T.add_node('S', label = 'Solution', style = 'filled',
                      color = 'lightblue', fillcolor = 'lightblue')
        T.add_node('P', label = 'Pruned', style = 'filled',
                      color = 'red', fillcolor = 'red')
        T.add_node('PC', label = 'Pruned \n Candidate', style = 'filled',
                      color = 'red', fillcolor = 'yellow')
    T.add_edge('C', 'I', style = 'invisible', arrowhead = 'none')
    T.add_edge('I', 'S', style = 'invisible', arrowhead = 'none')
    T.add_edge('S', 'P', style = 'invisible', arrowhead = 'none')
    T.add_edge('P', 'PC', style = 'invisible', arrowhead = 'none')
    T.create_cluster(['C', 'I', 'S', 'P', 'PC'], cluster_attrs)

    # Change to CyLP format
    cyOBJ = CyLPArray([-val for val in OBJ.values()]) # CyLP takes min
    cyMAT = np.matrix([MAT[v] for v in VARIABLES]).T
    cyRHS = CyLPArray(RHS)


    # The initial lower bound
    LB = -INFINITY
    # The number of LP's solved, and the number of nodes solved
    node_count = 1
    iter_count = 0
    lp_count = 0

    numCons = len(CONSTRAINTS)
    numVars = len(VARIABLES)
    # List of incumbent solution variable values
    opt = dict([(i, 0) for i in VARIABLES])
    pseudo_u = dict((i, (OBJ[i], 0)) for i in VARIABLES)
    pseudo_d = dict((i, (OBJ[i], 0)) for i in VARIABLES)
    print("===========================================")
    print("Starting Branch and Bound")
    if branch_strategy == MOST_FRACTIONAL:
        print("Most fractional variable")
    elif branch_strategy == FIXED_BRANCHING:
        print("Fixed order")
    elif branch_strategy == PSEUDOCOST_BRANCHING:
        print("Pseudocost brancing")
    else:
        print("Unknown branching strategy %s" %branch_strategy)
    if search_strategy == DEPTH_FIRST:
        print("Depth first search strategy")
    elif search_strategy == BEST_FIRST:
        print("Best first search strategy")
    else:
        print("Unknown search strategy %s" %search_strategy)
    print("===========================================")
    # List of candidate nodes
    Q = PriorityQueue()
    # The current tree depth
    cur_depth = 0
    cur_index = 0
    # Timer
    timer = time.time()
    Q.push(0, -INFINITY, (0, None, None, None, None, None, None))
    # Branch and Bound Loop
    while not Q.isEmpty():
        infeasible = False
        integer_solution = False
        (cur_index, parent, relax, branch_var, branch_var_value, sense,
        rhs) = Q.pop()
        if cur_index is not 0:
            cur_depth = T.get_node_attr(parent, 'level') + 1
        else:
            cur_depth = 0
        print("")
        print("----------------------------------------------------")
        print("")
        if LB > -INFINITY:
            print("Node: %s, Depth: %s, LB: %s" %(cur_index,cur_depth,LB))
        else:
            print("Node: %s, Depth: %s, LB: %s" %(cur_index,cur_depth,"None"))
        if relax is not None and relax <= LB:
            print("Node pruned immediately by bound")
            T.set_node_attr(parent, 'color', 'red')
            continue
        #====================================
        #    LP Relaxation
        #====================================
        # Compute lower bound by LP relaxation
        prob = CyLPModel()

        # CyLP do not allow change variable object without model
        if binary_vars:
            var = prob.addVariable('x', dim=len(VARIABLES))
            prob += 0 <= var <= 1
        else:
            var = prob.addVariable('x', dim=len(VARIABLES))
            prob += 0 <= var # To avoid random generated problems be unbounded


        prob += cyMAT * var <= RHS
        prob.objective = cyOBJ * var
        s = CyClpSimplex(prob)

        # Fix all prescribed variables
        branch_vars = []
        if cur_index is not 0:
            sys.stdout.write("Branching variables: ")
            branch_vars.append(branch_var)
            if sense == '>=':
                prob += var[int(branch_var[1:])] >= rhs # slice the name for index
            else:
                prob += var[int(branch_var[1:])] <= rhs # slice the name for index
            print(branch_var, end=' ')
            pred = parent
            while not str(pred) == '0':
                pred_branch_var = T.get_node_attr(pred, 'branch_var')
                pred_rhs = T.get_node_attr(pred, 'rhs')
                pred_sense = T.get_node_attr(pred, 'sense')
                if pred_sense == '<=':
                    prob += var[int(pred_branch_var[1:])] <= pred_rhs
                else:
                    prob += var[int(pred_branch_var[1:])] >= pred_rhs
                print(pred_branch_var, end=' ')
                branch_vars.append(pred_branch_var)
                pred = T.get_node_attr(pred, 'parent')
            print()
        # Solve the LP relaxation
        s = CyClpSimplex(prob)
        s.initialSolve()
        lp_count = lp_count +1

        if (s.getStatusCode() < 0):
            print('%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%')
            print(lp_count)
            print(s.getStatusCode())
            print(s.primal())
            print(s.objectiveValue)
            print(s.primalVariableSolution)
            print('%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%')

        # Check infeasibility
        #-1 - unknown e.g. before solve or if postSolve says not optimal
        #0 - optimal
        #1 - primal infeasible
        #2 - dual infeasible
        #3 - stopped on iterations or time
        #4 - stopped due to errors
        #5 - stopped by event handler (virtual int ClpEventHandler::event())
        infeasible = (s.getStatusCode() in [-1,1,3,4,5])
        # Print status
        if infeasible:
            print("LP Solved, status: Infeasible")
        else:
            print("LP Solved, status: %s, obj: %s" %(s.getStatusString(),-s.objectiveValue))

        if(s.getStatusCode() == 0):
            relax = -s.objectiveValue
            # Update pseudocost
            if branch_var != None:
                if sense == '<=':
                    pseudo_d[branch_var] = (
                    old_div((pseudo_d[branch_var][0]*pseudo_d[branch_var][1] +
                    old_div((T.get_node_attr(parent, 'obj') - relax),
                    (branch_var_value - rhs))),(pseudo_d[branch_var][1]+1)),
                    pseudo_d[branch_var][1]+1)
                else:
                    pseudo_u[branch_var] = (
                    old_div((pseudo_u[branch_var][0]*pseudo_d[branch_var][1] +
                     old_div((T.get_node_attr(parent, 'obj') - relax),
                     (rhs - branch_var_value))),(pseudo_u[branch_var][1]+1)),
                    pseudo_u[branch_var][1]+1)
            var_values = dict([(i, s.primalVariableSolution['x'][int(i[1:])]) for i in VARIABLES])
            integer_solution = 1
            for i in VARIABLES:
                if (abs(round(var_values[i]) - var_values[i]) > .001):
                    integer_solution = 0
                    break
            # Determine integer_infeasibility_count and
            # Integer_infeasibility_sum for scatterplot and such
            integer_infeasibility_count = 0
            integer_infeasibility_sum = 0.0
            for i in VARIABLES:
                if (var_values[i] not in set([0,1])):
                    integer_infeasibility_count += 1
                    integer_infeasibility_sum += min([var_values[i],
                                                      1.0-var_values[i]])
            if (integer_solution and relax>LB):
                LB = relax
                for i in VARIABLES:
                    # These two have different data structures first one
                    #list, second one dictionary
                    opt[i] = var_values[i]
                print("New best solution found, objective: %s" %relax)
                for i in VARIABLES:
                    if var_values[i] > 0:
                        print("%s = %s" %(i, var_values[i]))
            elif (integer_solution and relax<=LB):
                print("New integer solution found, objective: %s" %relax)
                for i in VARIABLES:
                    if var_values[i] > 0:
                        print("%s = %s" %(i, var_values[i]))
            else:
                print("Fractional solution:")
                for i in VARIABLES:
                    if var_values[i] > 0:
                        print("%s = %s" %(i, var_values[i]))
            #For complete enumeration
            if complete_enumeration:
                relax = LB - 1
        else:
            relax = INFINITY
        if integer_solution:
            print("Integer solution")
            BBstatus = 'S'
            status = 'integer'
            color = 'lightblue'
        elif infeasible:
            print("Infeasible node")
            BBstatus = 'I'
            status = 'infeasible'
            color = 'orange'
        elif not complete_enumeration and relax <= LB:
            print("Node pruned by bound (obj: %s, UB: %s)" %(relax,LB))
            BBstatus = 'P'
            status = 'fathomed'
            color = 'red'
        elif cur_depth >= numVars :
            print("Reached a leaf")
            BBstatus = 'fathomed'
            status = 'L'
        else:
            BBstatus = 'C'
            status = 'candidate'
            color = 'yellow'
        if BBstatus is 'I':
            if T.get_layout() == 'dot2tex':
                label = '\text{I}'
            else:
                label = 'I'
        else:
            label = "%.1f"%relax
        if iter_count == 0:
            if status is not 'candidate':
                integer_infeasibility_count = None
                integer_infeasibility_sum = None
            if status is 'fathomed':
                if T._incumbent_value is None:
                    print('WARNING: Encountered "fathom" line before '+\
                        'first incumbent.')
            T.AddOrUpdateNode(0, None, None, 'candidate', relax,
                             integer_infeasibility_count,
                             integer_infeasibility_sum,
                             label = label,
                             obj = relax, color = color,
                             style = 'filled', fillcolor = color)
            if status is 'integer':
                T._previous_incumbent_value = T._incumbent_value
                T._incumbent_value = relax
                T._incumbent_parent = -1
                T._new_integer_solution = True
    #           #Currently broken
    #           if ETREE_INSTALLED and T.attr['display'] == 'svg':
    #               T.write_as_svg(filename = "node%d" % iter_count,
    #                                 nextfile = "node%d" % (iter_count + 1),
    #                                 highlight = cur_index)
        else:
            _direction = {'<=':'L', '>=':'R'}
            if status is 'infeasible':
                integer_infeasibility_count = T.get_node_attr(parent,
                                     'integer_infeasibility_count')
                integer_infeasibility_sum = T.get_node_attr(parent,
                                     'integer_infeasibility_sum')
                relax = T.get_node_attr(parent, 'lp_bound')
            elif status is 'fathomed':
                if T._incumbent_value is None:
                    print('WARNING: Encountered "fathom" line before'+\
                        ' first incumbent.')
                    print('  This may indicate an error in the input file.')
            elif status is 'integer':
                integer_infeasibility_count = None
                integer_infeasibility_sum = None
            T.AddOrUpdateNode(cur_index, parent, _direction[sense],\
                                 status, relax,\
                                 integer_infeasibility_count,\
                                 integer_infeasibility_sum,\
                                 branch_var = branch_var,\
                                 branch_var_value = var_values[branch_var],\
                                 sense = sense, rhs = rhs, obj = relax,\
                                 color = color, style = 'filled',\
                                 label = label, fillcolor = color)
            if status is 'integer':
                T._previous_incumbent_value = T._incumbent_value
                T._incumbent_value = relax
                T._incumbent_parent = parent
                T._new_integer_solution = True
            # Currently Broken
    #           if ETREE_INSTALLED and T.attr['display'] == 'svg':
    #               T.write_as_svg(filename = "node%d" % iter_count,
    #                                 prevfile = "node%d" % (iter_count - 1),
    #                                 nextfile = "node%d" % (iter_count + 1),
    #                                 highlight = cur_index)
            if T.get_layout() == 'dot2tex':
                _dot2tex_label = {'>=':' \geq ', '<=':' \leq '}
                T.set_edge_attr(parent, cur_index, 'label',\
                                   str(branch_var) + _dot2tex_label[sense] +\
                                   str(rhs))
            else:
                T.set_edge_attr(parent, cur_index, 'label',\
                                   str(branch_var) + sense + str(rhs))
        iter_count += 1
        if BBstatus == 'C':
            # Branching:
            # Choose a variable for branching
            branching_var = None
            if branch_strategy == FIXED_BRANCHING:
                #fixed order
                for i in VARIABLES:
                    frac = min(s.primalVariableSolution['x'][int(i[1:])]-math.floor(s.primalVariableSolution['x'][int(i[1:])]),\
                               math.ceil(s.primalVariableSolution['x'][int(i[1:])]) - s.primalVariableSolution['x'][int(i[1:])])
                    if (frac > 0):
                        min_frac = frac
                        branching_var = i
                        # TODO(aykut): understand this break
                        break
            elif branch_strategy == MOST_FRACTIONAL:
                #most fractional variable
                min_frac = -1
                for i in VARIABLES:
                    frac = min(s.primalVariableSolution['x'][int(i[1:])]-math.floor(s.primalVariableSolution['x'][int(i[1:])]),\
                               math.ceil(s.primalVariableSolution['x'][int(i[1:])])- s.primalVariableSolution['x'][int(i[1:])])
                    if (frac> min_frac):
                        min_frac = frac
                        branching_var = i
            elif branch_strategy == PSEUDOCOST_BRANCHING:
                scores = {}
                for i in VARIABLES:
                    # find the fractional solutions
                    if (s.primalVariableSolution['x'][int(i[1:])] - math.floor(s.primalVariableSolution['x'][int(i[1:])])) != 0:
                        scores[i] = min(pseudo_u[i][0]*(1-s.primalVariableSolution['x'][int(i[1:])]),\
                                        pseudo_d[i][0]*s.primalVariableSolution['x'][int(i[1:])])
                    # sort the dictionary by value
                branching_var = sorted(list(scores.items()),
                                       key=lambda x : x[1])[-1][0]
            else:
                print("Unknown branching strategy %s" %branch_strategy)
                exit()
            if branching_var is not None:
                print("Branching on variable %s" %branching_var)
            #Create new nodes
            if search_strategy == DEPTH_FIRST:
                priority = (-cur_depth - 1, -cur_depth - 1)
            elif search_strategy == BEST_FIRST:
                priority = (-relax, -relax)
            elif search_strategy == BEST_ESTIMATE:
                priority = (-relax - pseudo_d[branching_var][0]*\
                                 (math.floor(s.primalVariableSolution['x'][int(branching_var[1:])]) -\
                                      s.primalVariableSolution['x'][int(branching_var[1:])]),\
                            -relax + pseudo_u[branching_var][0]*\
                                 (math.ceil(s.primalVariableSolution['x'][int(branching_var[1:])]) -\
                                      s.primalVariableSolution['x'][int(branching_var[1:])]))
            node_count += 1
            Q.push(node_count, priority[0], (node_count, cur_index, relax, branching_var,
                    var_values[branching_var],
                    '<=', math.floor(s.primalVariableSolution['x'][int(branching_var[1:])])))
            node_count += 1
            Q.push(node_count, priority[1], (node_count, cur_index, relax, branching_var,
                    var_values[branching_var],
                    '>=', math.ceil(s.primalVariableSolution['x'][int(branching_var[1:])])))
            T.set_node_attr(cur_index, color, 'green')
        if T.root is not None and display_interval is not None and\
                iter_count%display_interval == 0:
            T.display(count=iter_count)

    timer = int(math.ceil((time.time()-timer)*1000))
    print("")
    print("===========================================")
    print("Branch and bound completed in %sms" %timer)
    print("Strategy: %s" %branch_strategy)
    if complete_enumeration:
        print("Complete enumeration")
    print("%s nodes visited " %node_count)
    print("%s LP's solved" %lp_count)
    print("===========================================")
    print("Optimal solution")
    #print optimal solution
    for i in sorted(VARIABLES):
        if opt[i] > 0:
            print("%s = %s" %(i, opt[i]))
    print("Objective function value")
    print(LB)
    print("===========================================")
    if T.attr['display'] is not 'off':
        T.display(count=iter_count)
    T._lp_count = lp_count
    return LB,opt