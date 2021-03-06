'''
File: cylpBranchAndBound.py
Author: Yutong Dai and Muqing Zheng
File Created: 2020-05-12 23:40
Last Modified: 2020-05-14 01:33
--------------------------------------------
Description:
Modified based on coinor.grumpy
'''
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


RELIABILITY_BRANCHING = 'Reliability Branching'
HYBRID = 'hybrid'


def BranchAndBound(T, CONSTRAINTS, VARIABLES, OBJ, MAT, RHS,
                   branch_strategy=MOST_FRACTIONAL,
                   search_strategy=DEPTH_FIRST,
                   complete_enumeration=False,
                   display_interval=None,
                   binary_vars=True,
                   solver='dynamic',
                   rel_param=(4, 3, 1 / 6, 5),
                   more_return=False
                   ):
    """
        solver: 
            dynamic       - initialSolve
            primalSimplex - initialPrimalSolve 
            dualSimplex   - initialDualSolve

        Parameter Tuple for Reliability Branching
        rel_param = (eta_rel,gamma,mu,lambda):
            eta_rel = 0       - psesudocost branching
            eta_rel = 1       - psesudocost branching with strong branching initialization
            eta_rel = 4,8     - best performing reliability branching rules
            eta_rel = inifity - strong branching
            gamma             - max number of simplex iterations in score calculation
            mu                - score factor, a number between 0 and 1. Paper uses 1/6
            lambda            - if max score is not updated for lambda 
                                consecutive iterations, stop.
        more_return:
            False - return maximizer and max 
            True  - also return a dict of stats(time, tree size, LP solved)
    """
    ACTUAL_BRANCH_STRATEGY = branch_strategy
    # reliability branching parameters
    eta_rel, gamma, mu, lam = rel_param
    # hybrid branching parameters
    total_num_pivot = average_num_pivot = 0
    # translate problems into cylp format
    cyOBJ = CyLPArray([-val for val in OBJ.values()])
    cyMAT = np.matrix([MAT[v] for v in VARIABLES]).T
    cyRHS = CyLPArray(RHS)
    OBJ = cyOBJ
    MAT = cyMAT
    RHS = cyRHS
    if T.get_layout() == 'dot2tex':
        cluster_attrs = {'name': 'Key', 'label': r'\text{Key}', 'fontsize': '12'}
        T.add_node('C', label=r'\text{Candidate}', style='filled',
                   color='yellow', fillcolor='yellow')
        T.add_node('I', label=r'\text{Infeasible}', style='filled',
                   color='orange', fillcolor='orange')
        T.add_node('S', label=r'\text{Solution}', style='filled',
                   color='lightblue', fillcolor='lightblue')
        T.add_node('P', label=r'\text{Pruned}', style='filled',
                   color='red', fillcolor='red')
        T.add_node('PC', label=r'\text{Pruned}$\\ $\text{Candidate}', style='filled',
                   color='red', fillcolor='yellow')
    else:
        cluster_attrs = {'name': 'Key', 'label': 'Key', 'fontsize': '12'}
        T.add_node('C', label='Candidate', style='filled',
                   color='yellow', fillcolor='yellow')
        T.add_node('I', label='Infeasible', style='filled',
                   color='orange', fillcolor='orange')
        T.add_node('S', label='Solution', style='filled',
                   color='lightblue', fillcolor='lightblue')
        T.add_node('P', label='Pruned', style='filled',
                   color='red', fillcolor='red')
        T.add_node('PC', label='Pruned \n Candidate', style='filled',
                   color='red', fillcolor='yellow')
    T.add_edge('C', 'I', style='invisible', arrowhead='none')
    T.add_edge('I', 'S', style='invisible', arrowhead='none')
    T.add_edge('S', 'P', style='invisible', arrowhead='none')
    T.add_edge('P', 'PC', style='invisible', arrowhead='none')
    T.create_cluster(['C', 'I', 'S', 'P', 'PC'], cluster_attrs)
    # The initial lower bound
    LB = -INFINITY
    # The number of LP's solved, and the number of nodes solved
    node_count = 1
    iter_count = 0
    lp_count = 0  # The problems that are fully solved during
    # Reliability and Hybrid branching is also couned here
    # For reliability branching
    half_solved = 0  # record number problems been halfly solved when calculate scores
    full_solved = 0  # record number problems been fully solved when calculate scores

    numVars = len(VARIABLES)
    # List of incumbent solution variable values
    opt = dict([(i, 0) for i in range(len(VARIABLES))])
    pseudo_u = dict((i, (-OBJ[i], 0)) for i in range(len(VARIABLES)))
    pseudo_d = dict((i, (-OBJ[i], 0)) for i in range(len(VARIABLES)))

    print("===========================================")
    print("Starting Branch and Bound")
    if branch_strategy == MOST_FRACTIONAL:
        print("Most fractional variable")
    elif branch_strategy == FIXED_BRANCHING:
        print("Fixed order")
    elif branch_strategy == PSEUDOCOST_BRANCHING:
        print("Pseudocost brancing")
    elif branch_strategy == RELIABILITY_BRANCHING:
        print("Reliability branching")
    elif branch_strategy == HYBRID:
        print('Hybrid strong/pseduocost branching')
    else:
        print("Unknown branching strategy %s" % branch_strategy)
    if search_strategy == DEPTH_FIRST:
        print("Depth first search strategy")
    elif search_strategy == BEST_FIRST:
        print("Best first search strategy")
    elif search_strategy == BEST_ESTIMATE:
        print("Best estimate search strategy")
    else:
        print("Unknown search strategy %s" % search_strategy)
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
        # maximum allowed strong branch performed
        if branch_strategy == HYBRID and cur_depth > max(int(len(VARIABLES) * 0.2), 5):
            branch_strategy = PSEUDOCOST_BRANCHING
            print("Switch from strong branch to psedocost branch")
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
            print("Node: %s, Depth: %s, LB: %s" % (cur_index, cur_depth, LB))
        else:
            print("Node: %s, Depth: %s, LB: %s" % (cur_index, cur_depth, "None"))
        if relax is not None and relax <= LB:
            print("Node pruned immediately by bound")
            T.set_node_attr(parent, 'color', 'red')
            continue
        # ====================================
        #    LP Relaxation
        # ====================================
        # Compute lower bound by LP relaxation
        prob = CyLPModel()
        if binary_vars:
            x = prob.addVariable('x', dim=len(VARIABLES))
            prob += 0 <= x <= 1
        else:
            x = prob.addVariable('x', dim=len(VARIABLES))
        prob.objective = OBJ * x
        prob += MAT * x <= RHS
        # Fix all prescribed variables
        branch_vars = []
        if cur_index is not 0:
            sys.stdout.write("Branching variables: ")
            branch_vars.append(branch_var)
            if sense == '>=':
                prob += x[branch_var] >= rhs
            else:
                prob += x[branch_var] <= rhs
            print('x_{}'.format(branch_var), end=' ')
            pred = parent
            while not str(pred) == '0':
                pred_branch_var = T.get_node_attr(pred, 'branch_var')
                pred_rhs = T.get_node_attr(pred, 'rhs')
                pred_sense = T.get_node_attr(pred, 'sense')
                if pred_sense == '<=':
                    prob += x[pred_branch_var] <= pred_rhs
                else:
                    prob += x[pred_branch_var] >= pred_rhs
                print(pred_branch_var, end=' ')
                branch_vars.append(pred_branch_var)
                pred = T.get_node_attr(pred, 'parent')
            print()
        # Solve the LP relaxation
        s = CyClpSimplex(prob)
        if solver == 'primalSimplex':
            s.initialPrimalSolve()
        elif solver == 'dualSimplex':
            s.initialDualSolve()
        else:
            s.initialSolve()
        lp_count = lp_count + 1
        total_num_pivot += s.iteration
        average_num_pivot = total_num_pivot / lp_count
        # Check infeasibility
        # -1 - unknown e.g. before solve or if postSolve says not optimal
        # 0 - optimal
        # 1 - primal infeasible
        # 2 - dual infeasible
        # 3 - stopped on iterations or time
        # 4 - stopped due to errors
        # 5 - stopped by event handler (virtual int ClpEventHandler::event())
        infeasible = (s.getStatusCode() in [1, 2])
        # Print status
        if infeasible:
            print("LP Solved, status: Infeasible")
        else:
            print("LP Solved, status: %s, obj: %s" % (s.getStatusString(),
                                                      s.objectiveValue))
        if(s.getStatusCode() == 0):
            relax = -round(s.objectiveValue,7)
            # Update pseudocost
            if branch_var != None:
                if sense == '<=':
                    pseudo_d[branch_var] = (
                        old_div((pseudo_d[branch_var][0] * pseudo_d[branch_var][1] +
                                 old_div((T.get_node_attr(parent, 'obj') - relax),
                                         (branch_var_value - rhs))),
                                (pseudo_d[branch_var][1] + 1)),
                        pseudo_d[branch_var][1] + 1)
                else:
                    pseudo_u[branch_var] = (
                        old_div((pseudo_u[branch_var][0] * pseudo_d[branch_var][1] +
                                 old_div((T.get_node_attr(parent, 'obj') - relax),
                                         (rhs - branch_var_value))),
                                (pseudo_u[branch_var][1] + 1)),
                        pseudo_u[branch_var][1] + 1)
            var_values = dict([(i, round(s.primalVariableSolution['x'][i],7))
                               for i in range(len(VARIABLES))])
            integer_solution = 1
            for i in range(len(VARIABLES)):
                if (abs(round(var_values[i]) - var_values[i]) > .001):
                    integer_solution = 0
                    break
            # Determine integer_infeasibility_count and
            # Integer_infeasibility_sum for scatterplot and such
            integer_infeasibility_count = 0
            integer_infeasibility_sum = 0.0
            for i in range(len(VARIABLES)):
                if (var_values[i] not in set([0, 1])):
                    integer_infeasibility_count += 1
                    integer_infeasibility_sum += min([var_values[i],
                                                      1.0 - var_values[i]])
            if (integer_solution and relax > LB):
                LB = relax
                for i in range(len(VARIABLES)):
                    # These two have different data structures first one
                    # list, second one dictionary
                    opt[i] = var_values[i]
                print("New best solution found, objective: %s" % relax)
                for i in range(len(VARIABLES)):
                    if var_values[i] > 0:
                        print("%s = %s" % (i, var_values[i]))
            elif (integer_solution and relax <= LB):
                print("New integer solution found, objective: %s" % relax)
                for i in range(len(VARIABLES)):
                    if var_values[i] > 0:
                        print("%s = %s" % (i, var_values[i]))
            else:
                print("Fractional solution:")
                for i in range(len(VARIABLES)):
                    if var_values[i] > 0:
                        print("x%s = %s" % (i, var_values[i]))
            # For complete enumeration
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
            print("Node pruned by bound (obj: %s, UB: %s)" % (relax, LB))
            BBstatus = 'P'
            status = 'fathomed'
            color = 'red'
        elif cur_depth >= numVars:
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
            label = "%.1f" % relax
        if iter_count == 0:
            if status is not 'candidate':
                integer_infeasibility_count = None
                integer_infeasibility_sum = None
            if status is 'fathomed':
                if T._incumbent_value is None:
                    print('WARNING: Encountered "fathom" line before ' +
                          'first incumbent.')
            T.AddOrUpdateNode(0, None, None, 'candidate', relax,
                              integer_infeasibility_count,
                              integer_infeasibility_sum,
                              label=label,
                              obj=relax, color=color,
                              style='filled', fillcolor=color)
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
            _direction = {'<=': 'L', '>=': 'R'}
            if status is 'infeasible':
                integer_infeasibility_count = T.get_node_attr(parent,
                                                              'integer_infeasibility_count')
                integer_infeasibility_sum = T.get_node_attr(parent,
                                                            'integer_infeasibility_sum')
                relax = T.get_node_attr(parent, 'lp_bound')
            elif status is 'fathomed':
                if T._incumbent_value is None:
                    print('WARNING: Encountered "fathom" line before' +
                          ' first incumbent.')
                    print('  This may indicate an error in the input file.')
            elif status is 'integer':
                integer_infeasibility_count = None
                integer_infeasibility_sum = None
            T.AddOrUpdateNode(cur_index, parent, _direction[sense],
                              status, relax,
                              integer_infeasibility_count,
                              integer_infeasibility_sum,
                              branch_var=branch_var,
                              branch_var_value=var_values[branch_var],
                              sense=sense, rhs=rhs, obj=relax,
                              color=color, style='filled',
                              label=label, fillcolor=color)
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
                _dot2tex_label = {'>=': ' \geq ', '<=': ' \leq '}
                T.set_edge_attr(parent, cur_index, 'label',
                                str(branch_var) + _dot2tex_label[sense] +
                                str(rhs))
            else:
                T.set_edge_attr(parent, cur_index, 'label',
                                str(branch_var) + sense + str(rhs))
        iter_count += 1
        if BBstatus == 'C':
            # Branching:
            # Choose a variable for branching
            branching_var = None
            if branch_strategy == FIXED_BRANCHING:
                # fixed order
                for i in range(len(VARIABLES)):
                    frac = min(var_values[i] - math.floor(var_values[i]),
                               math.ceil(var_values[i]) - var_values[i])
                    if (frac > 0):
                        min_frac = frac
                        branching_var = i
                        # TODO(aykut): understand this break
                        break
            elif branch_strategy == MOST_FRACTIONAL:
                # most fractional variable
                min_frac = -1
                for i in range(len(VARIABLES)):
                    frac = min(var_values[i] - math.floor(var_values[i]),
                               math.ceil(var_values[i]) - var_values[i])
                    if (frac > min_frac):
                        min_frac = frac
                        branching_var = i
            elif branch_strategy == PSEUDOCOST_BRANCHING:
                scores = {}
                for i in range(len(VARIABLES)):
                    # find the fractional solutions
                    if abs(var_values[i] - math.floor(var_values[i])) > 1e-8:
                        scores[i] = min(pseudo_u[i][0] * (math.ceil(var_values[i])
                                                          - var_values[i]),
                                        pseudo_d[i][0] * (var_values[i]
                                                          - math.floor(var_values[i])))
                # sort the dictionary by value
                branching_var = sorted(list(scores.items()), key=lambda x: x[1])[-1][0]

            elif branch_strategy == RELIABILITY_BRANCHING:
                # Calculating Scores
                # The algorithm in paper is different from the one in Grumpy
                # I will try to use paper notations
                scores = {}
                for i in range(len(VARIABLES)):
                    # find the fractional solutions
                    if abs(var_values[i] - math.floor(var_values[i])) > 1e-8:
                        qp = pseudo_u[i][0] * (math.ceil(var_values[i])
                                               - var_values[i])  # q^+
                        qm = pseudo_d[i][0] * (var_values[i]
                                               - math.floor(var_values[i]))  # q^^-
                        scores[i] = (1 - mu) * min(qm, qp) + mu * max(qm, qp)

                # sort the dictionary by value
                candidate_vars = [en[0] for en in sorted(list(scores.items()), key=lambda x: x[1], reverse=True)]

                no_change = 0  # number of iterations that maximum of scores is not changed
                smax = scores[candidate_vars[0]]  # current maximum of scores
                for i in candidate_vars:
                    if min(pseudo_d[i][1], pseudo_u[i][1]) < eta_rel:
                        qp = pseudo_u[i][0] * (math.ceil(var_values[i]) - var_values[i])  # q^+
                        qm = pseudo_d[i][0] * (var_values[i] - math.floor(var_values[i]))  # q^^-

                        # left subproblem/down direction
                        s_left = CyClpSimplex(prob)
                        s_left += x[i] <= math.floor(var_values[i])
                        s_left.maxNumIteration = gamma  # solve for fixed number of iterations
                        s_left.dual()
                        if s_left.getStatusCode() == 0:
                            qm = relax + s_left.objectiveValue  # use a more reliable source to update q^-
                            full_solved = full_solved + 1
                            lp_count = lp_count + 1  # If the LP is fully solved, counter plus one
                        elif s_left.getStatusCode() == 3:
                            qm = relax + s_left.objectiveValue  # use a more reliable source to update q^-
                            half_solved = half_solved + 1

                        # right subproblem/up direction
                        s_right = CyClpSimplex(prob)
                        s_right += x[i] >= math.ceil(var_values[i])
                        s_right.maxNumIteration = gamma  # solve for fixed number of iterations
                        s_right.dual()
                        if s_right.getStatusCode() == 0:
                            qp = relax + s_right.objectiveValue   # use a more reliable source to update q^+
                            full_solved = full_solved + 1
                            lp_count = lp_count + 1  # If the LP is fully solved, counter plus one
                        elif s_right.getStatusCode() == 3:
                            qp = relax + s_right.objectiveValue  # use a more reliable source to update q^+
                            half_solved = half_solved + 1

                        scores[i] = (1 - mu) * min(qm, qp) + mu * max(qm, qp)
                        if (smax == scores[i]):
                            no_change += 1
                        elif (smax <= scores[i]):
                            no_change = 0
                            smax = scores[i]
                        else:
                            no_change = 0

                    if no_change >= lam:
                        break
                branching_var = sorted(list(scores.items()), key=lambda x: x[1])[-1][0]

            elif branch_strategy == HYBRID:
                scores = {}
                for i in range(len(VARIABLES)):
                    # find the fractional solutions
                    if abs(var_values[i] - math.floor(var_values[i])) > 1e-8:
                        scores[i] = min(pseudo_u[i][0] * (math.ceil(var_values[i])
                                                          - var_values[i]),
                                        pseudo_d[i][0] * (var_values[i]
                                                          - math.floor(var_values[i])))
                candidate_vars = [en[0] for en in sorted(list(scores.items()), key=lambda x: x[1], reverse=True)]
                restricted_candidate_vars = candidate_vars[:max(1, int(0.5 * len(candidate_vars)))]
                # print("Subset of candidate variables:")
                # print(restricted_candidate_vars)
                best_progress = 0
                branch_candidate = None
                for i in restricted_candidate_vars:
                    s = CyClpSimplex(prob)
                    s += math.floor(var_values[i]) <= x[i] <= math.ceil(var_values[i])
                    s.maxNumIteration = average_num_pivot * 2
                    s.dual()
                    if s.getStatusCode() == 0:
                        lp_count += 1
                    progress = relax - (-s.objectiveValue)
                    if (progress - best_progress) > 1e-8:
                        branch_candidate = i
                        best_progress = progress
                if branch_candidate is None:
                    branch_candidate = restricted_candidate_vars[0]
                branching_var = branch_candidate

            else:
                print("Unknown branching strategy %s" % branch_strategy)
                exit()
            if branching_var is not None:
                print("Branching on variable %s" % branching_var)
            # Create new nodes
            if search_strategy == DEPTH_FIRST:
                priority = (-cur_depth - 1, -cur_depth - 1)
            elif search_strategy == BEST_FIRST:
                priority = (-relax, -relax)
            elif search_strategy == BEST_ESTIMATE:
                priority = (-relax - pseudo_d[branching_var][0] *
                            (math.floor(var_values[branching_var]) - var_values[branching_var]),
                            -relax + pseudo_u[branching_var][0] *
                            (math.ceil(var_values[branching_var]) - var_values[branching_var]))
            node_count += 1
            Q.push(node_count, priority[0], (node_count, cur_index, relax, branching_var,
                                             var_values[branching_var],
                                             '<=', math.floor(var_values[branching_var])))
            node_count += 1
            Q.push(node_count, priority[1], (node_count, cur_index, relax, branching_var,
                                             var_values[branching_var],
                                             '>=', math.ceil(var_values[branching_var])))
            T.set_node_attr(cur_index, color, 'green')
        if T.root is not None and display_interval is not None and\
                iter_count % display_interval == 0:
            T.display(count=iter_count)

    timer = int(math.ceil((time.time() - timer) * 1000))
    print("")
    print("===========================================")
    print("Branch and bound completed in %sms" % timer)
    print("Strategy: %s" % ACTUAL_BRANCH_STRATEGY)
    if complete_enumeration:
        print("Complete enumeration")
    print("%s nodes visited " % node_count)
    print("%s LP's solved" % lp_count)
    print("===========================================")
    print("Optimal solution")
    # print optimal solution
    for i in range(len(VARIABLES)):
        if opt[i] > 0:
            print("x%s = %s" % (i, opt[i]))
    print("Objective function value")
    print(LB)
    print("===========================================")
    if T.attr['display'] is not 'off':
        T.display(count=iter_count)
    T._lp_count = lp_count

    if more_return:
        stat = {'Time': timer, 'Size': node_count, 'LP Solved': lp_count}
        if branch_strategy == RELIABILITY_BRANCHING:
            stat['LP Solved for Bounds'] = lp_count - full_solved
            stat['Halfly Solved'] = half_solved
            stat['Fully Solved'] = full_solved
        return opt, LB, stat
    
    return opt, LB


if __name__ == '__main__':
    from generator import GenerateRandomMIP
    T = BBTree()
    T.set_display_mode('xdot')
    CONSTRAINTS, VARIABLES, OBJ, MAT, RHS = GenerateRandomMIP(numVars=30, numCons=20, rand_seed=418, density=0.3)
    _, _, stat1 = BranchAndBound(T, CONSTRAINTS, VARIABLES, OBJ, MAT, RHS,
                                 branch_strategy=RELIABILITY_BRANCHING,
                                 search_strategy=DEPTH_FIRST,
                                 display_interval=10000,
                                 solver='primalSimplex',
                                 binary_vars=True,
                                 more_return=True
                                 )
    T = BBTree()
    T.set_display_mode('xdot')
    _, _, stat2 = BranchAndBound(T, CONSTRAINTS, VARIABLES, OBJ, MAT, RHS,
                                 branch_strategy=PSEUDOCOST_BRANCHING,
                                 search_strategy=DEPTH_FIRST,
                                 display_interval=10000,
                                 solver='primalSimplex',
                                 binary_vars=True,
                                 more_return=True
                                 )
    print(RELIABILITY_BRANCHING)
    print(stat1)
    print(PSEUDOCOST_BRANCHING)
    print(stat2)
