﻿from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext

from activity import action as _action
from mathcontent.forms import MathContentForm
from permissions.constants import VIEW
from task.models import Task
from skoljka.utils.decorators import ajax, response, require

from solution.models import HTML_INFO, Solution, STATUS, _update_solved_count

from datetime import datetime
import json

# ... trenutacna implementacija rjesenja je dosta diskutabilna

# TODO: task permissions (?)
@response('solution_detail.html')
def detail(request, solution_id):
    # default is True
    show_task = not request.user.is_authenticated() \
        or request.user.get_profile().show_solution_task

    args = ['task.content'] if show_task else []

    solution = get_object_or_404(Solution.objects.select_related('content',
        'author', 'task', *args), id=solution_id)

    if not solution.status == STATUS['submitted']:
        return (404, u'Rješenje nije dostupno.')
    if not solution.task.user_has_perm(request.user, VIEW):
        return (403, u'Zadatak nije dostupan.')

    if solution.correctness_avg:
        ratings = solution.correctness.select_related('user')
    else:
        ratings = []

    # If I can view the solution, it means I can view the Task.
    # Note that I might not even met the actual prerequisites, but it means
    # I do have the solution, or I have VIEW_SOLUTION permission.
    # (look at the docs of .prerequisites in task/models.py)
    solution.task.cache_prerequisites_met = True

    can_view, obfuscate = solution.check_accessibility(request.user)

    if not can_view:
        if solution.task.solution_settings == Task.SOLUTIONS_NOT_VISIBLE:
            return (403, u'Autor zadatka je onemogućio pristup rješenjima '  \
                u'drugih korisnika.')
        else: # Task.SOLUTIONS_VISIBLE_IF_ACCEPTED
            return (403, u'Rješenje dostupno samo korisnicima s točnim '
                u'vlastitim rješenjem.')

    return {
        'can_view': can_view,
        'obfuscate': obfuscate,
        'ratings': ratings,
        'show_task': show_task,
        'solution': solution,
    }


def _do_mark(request, solution, task):
    """
        Update solution status:
            As Solved
            To Do
            Blank

        Or mark / unmark official flag

        Creates Solution if it doesn't exist (in that case Task is given).

        Returns None if no error.
    """

    action = request.POST['action']

    # check requset and privileges
    if action not in ['official0', 'official1', 'blank', 'as_solved', 'todo']:
        return (403, u'Action "%s" not valid.' % action)

    if action in ['official0', 'official1'] and task.author != request.user \
            and not request.user.has_perm('solution.mark_as_official_solution'):
        return (403, u'No permission to mark as official solution.')

    if not task.solvable:
        return (403, u'This task is not solvable!')

    # as_solved, todo, blank
    if solution is None:
        # Check if the task is visible to the user.
        if not task.user_has_perm(request.user, VIEW):
            return (403, u'Zadatak nije dostupan.')
        solution, dummy = Solution.objects.get_or_create(task=task, author=request.user)

    if solution.author_id != request.user.id:
        return (403, 'Not allowed to modify this solution.')


    # keep track of the number of solutions for the task
    was_solved = solution.is_solved()


    # update
    if action in ['official0', 'official1']:
        solution.is_official = action == 'official1'
    elif action in ['blank', 'as_solved', 'todo']:
        if action != 'blank':
            solution.date_created = datetime.now()
        solution.status = STATUS[action]

    solution.save()


    # log the action
    # TODO: use signals!
    if action in ['official1', 'as_solved', 'todo']:
        type_desc = {'official1': _action.SOLUTION_AS_OFFICIAL,
                     'as_solved': _action.SOLUTION_AS_SOLVED,
                     'todo': _action.SOLUTION_TODO,
            }
        _action.replace_or_add(request.user, type_desc[action],
            action_object=solution, target=task)
    elif action == 'official0':
        # temporary solution...
        _action.remove(request.user, type=_action.SOLUTION_AS_OFFICIAL[0],
            action_object=solution, target=task)
    elif action == 'blank':
        _action.remove(request.user, type=_action.SOLUTION_SEND,
            action_object=solution, target=task)


    # update solved count if necessary
    # TODO: use signals!
    delta = solution.is_solved() - was_solved
    if delta:
        _update_solved_count(delta, task, request.user.get_profile())

    return None     # ok

@ajax(post=['action'])
@response()
def task_ajax(request, task_id):
    """
        Called from task tooltip.
    """
    task = get_object_or_404(Task, pk=task_id)

    ret_value = _do_mark(request, None, task)
    if ret_value:
        return ret_value

    # Return html info for given action as JSON.
    info = HTML_INFO[STATUS[request.POST['action']]]
    if not info['tr_class'] and task.hidden:
        info['tr_class'] = 'task-hidden'
    return json.dumps(info)


@require(post='action')
@response()
@login_required
def mark(request, task_id):
    """
        Called from Task view
    """
    task = get_object_or_404(Task, pk=task_id)

    # _do_mark will create Solution if it doesn't exist, and check Task
    # permissions
    ret_value = _do_mark(request, None, task)

    return ret_value or (response.REDIRECT, '/task/%d/' % int(task_id))


@require(post='action')
@response()
@login_required
def edit_mark(request, solution_id):
    """
        Called from Solution view
    """
    solution = get_object_or_404(Solution.objects.select_related('task'),
        id=solution_id)

    # Not necessary to check Task permissions. If user was able to create
    # Solution, then he/she is able to edit it.
    ret_value = _do_mark(request, solution, solution.task)

    if ret_value:
        return ret_value
    if request.POST['action'] in ['official0', 'official1']:
        return (solution.get_absolute_url(), )
    return (solution.task.get_absolute_url(), )


@login_required
@response('solution_submit.html')
def submit(request, task_id=None, solution_id=None):
    if solution_id:
        solution = get_object_or_404(Solution, pk=solution_id)
        task = solution.task
        edit = True
    elif task_id:
        task = get_object_or_404(Task, pk=task_id)
        edit = False
    else:
        return 404

    if not task.solvable:
        return (403, u'This task is not solvable!')

    if not edit:
        # First check Task permissions.
        if not task.user_has_perm(request.user, VIEW):
            return (403, u'Zadatak nije dostupan.')
        solution, dummy = Solution.objects.get_or_create(task=task, author=request.user)

    math_content = solution.content

    if request.method == 'POST':
        math_content_form = MathContentForm(request.POST, instance=math_content)
        if math_content_form.is_valid():
            math_content = math_content_form.save()

            was_solved = solution.is_solved()

            solution.content = math_content
            solution.status = STATUS['submitted']
            solution.date_created = datetime.now()
            solution.save()
            if not edit:
                _action.replace_or_add(request.user, _action.SOLUTION_SUBMIT,
                    action_object=solution, target=task)

            # update solved count if necessary
            delta = solution.is_solved() - was_solved
            if delta:
                _update_solved_count(delta, task, request.user.get_profile())

            return ("/solution/%d/" % (solution.id,),)
    else:
        math_content_form = MathContentForm(instance=math_content)

    return {
        'action_url': request.path,
        'form': math_content_form,
        'task': task,
    }

def _is_valid_status(status):
    if not status:
        return True
    L = status.split(',')
    return 'blank' not in L and all((x in STATUS for x in L))

@response('solution_list.html')
def solution_list(request, task_id=None, user_id=None, status=None):
    """
        Outputs list of solutions related to
        specific task if task_id is defined,
        specific user if user_id is defined.
        If some ID is not defined, skips that condition.
    """
    # Currently, even if the user can't view some of the solution (due to task
    # settings), he/she may still view the correctness.
    # If necessary, add new option to task.solution_settings, for example, to
    # completely remove solutions from solution list etc.

    if status is None:
        status = request.GET.get('status', None)
        if status is not None and not _is_valid_status(status):
            return (response.BAD_REQUEST, 'Invalid status.')

    # detailed_status > 0 is also a possible solution (mysql could use an index)
    # but there are too few blank solutions for this to have any effect
    L = Solution.objects.filter_visible_tasks_for_user(request.user)    \
        .exclude(status=STATUS['blank'])

    task = None
    author = None   # 'user' is a template reserved word

    empty_message = u''
    if task_id is not None:
        task = get_object_or_404(Task, pk=task_id)
        if not task.user_has_perm(request.user, VIEW):
            return (403, u'Zadatak nije dostupan.') # bye
        L = L.filter(task=task)
        empty_message = u'Nema traženih rješenja za ovaj zadatak'

    if user_id is not None:
        author = get_object_or_404(User, pk=user_id)
        L = L.filter(author=author)
        empty_message = u'Nema traženih rješenja za ovog korisnika'

    L = L.select_related('author', 'content', 'task')

    return {
        'empty_message': empty_message,
        'filter_by_status': status,
        'solutions': L.order_by('-date_created'),
        'task': task,
        'author': author,
        'submitted_active': 'active' if status == [u'submitted'] else '',
    }
