﻿from django.contrib.admin.models import LogEntry, CHANGE
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.contenttypes.models import ContentType
from django.http import Http404, HttpResponse, HttpResponseForbidden, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.template.defaultfilters import slugify
from django.utils import simplejson

from permissions.constants import VIEW, EDIT, EDIT_PERMISSIONS
from permissions.models import ObjectPermission
from task.models import Task
from skoljka.utils.decorators import response

from folder.models import Folder
from folder.forms import FolderForm, FolderAdvancedCreateForm
from folder.utils import refresh_cache, get_folder_template_data

@login_required
def select_task(request, task_id):
    folder = request.user.profile.selected_folder
    if not request.is_ajax() or folder is None:
        return HttpResponseBadRequest()
    if not folder.user_has_perm(request.user, EDIT):
        return HttpResponseForbidden('Not allowed to edit this folder.')

    task = get_object_or_404(Task, id=task_id)
    if not task.user_has_perm(request.user, VIEW):
        return HttpResponseForbidden('Not allowed to view this task.')

    if task in folder.tasks.all():
        folder.tasks.remove(task)
        response = '0'
    else:
        folder.tasks.add(task)
        response = '1'

    return HttpResponse(response)


@login_required
def select(request, id):
    folder = get_object_or_404(Folder, id=id)
    if not folder.user_has_perm(request.user, EDIT):
        return HttpResponseForbidden('Not allowed to edit this folder.')

    profile = request.user.profile
    if profile.selected_folder == folder:
        profile.selected_folder = None
        response = 0
    else:
        profile.selected_folder = folder
        response = 1

    profile.save()
    #return HttpResponse(FOLDER_EDIT_LINK_CONTENT[response])
    return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))


@login_required
def detail_by_id(request, id):
    folder = get_object_or_404(Folder, id=id)
    return HttpResponseRedirect(folder.get_absolute_url())


@response('folder_detail.html')
def view(request, id=None, description=u''):
    if id is None:
        folder = Folder.objects.get(parent_id__isnull=True)
    else:
        folder = get_object_or_404(Folder, id=id)

    data = folder.get_template_data(request.user, Folder.DATA_ALL)
    if not data:
        raise Http404

    # Some additional tuning
    data['tasks'] = data['tasks'].select_related('author')

    folder = data.get('folder')
    if folder and folder.editable and folder.user_has_perm(request.user, EDIT):
        data['edit_link'] = True
        if not data['tag_list']:
            data['select_link'] = True

    return data

@login_required
@response('folder_new.html')
def new(request, folder_id=None):
    # Analogous to task.models.new

    if folder_id:
        folder = get_object_or_404(Folder, id=folder_id)
        edit = True
        old_parent_id = folder.parent_id
    else:
        folder = old_parent_id = None
        edit = False

    data = {}

    if edit:
        if not folder.editable:
            return response.FORBIDDEN

        permissions = folder.get_user_permissions(request.user)

        if EDIT not in permissions:
            return response.FORBIDDEN

        if EDIT_PERMISSIONS in permissions:
            data['can_edit_permissions'] = True
            data['content_type'] = ContentType.objects.get_for_model(Folder)

        data['children'] = children = list(Folder.objects   \
            .for_user(request.user, VIEW)                   \
            .filter(parent=folder).order_by('parent_index').distinct())


    if request.method == 'POST':
        folder_form = FolderForm(request.POST, instance=folder, user=request.user)
        if folder_form.is_valid():
            folder = folder_form.save(commit=False)

            folder.slug = slugify(folder.name)

            if not edit:
                folder.author = request.user
            else:
                for x in children:
                    parent_index = request.POST.get('child-{}'.format(x.id))
                    if parent_index is not None \
                            and x.parent_index != parent_index:
                        x.parent_index = parent_index
                        x.save()

                # Update order...
                children.sort(key=lambda x: x.parent_index)

            folder.save()

            # Refresh Folder cache.
            # TODO: Optimize, update only necessary folders.
            if old_parent_id != folder.parent_id:
                refresh_cache(Folder.objects.all())

            
            # return HttpResponseRedirect(folder.get_absolute_url())
    else:
        folder_form = FolderForm(instance=folder, user=request.user)

    if edit:
        data.update(folder.get_template_data(request.user, Folder.DATA_MENU))

    data['form'] = folder_form
    data['edit'] = edit

    if request.user.has_perm('folder.advanced_create'):
        data['advanced_create_permission'] = True

    return data


def _dict_to_object(d):
    class Struct(object):
        def __init__(self, d):
            self.__dict__.update(d)

    return Struct(d)

def _create_folders(author, parent, structure, p):
    vars = {'p': p}

    level, separator, rest = structure.partition('|')
    rest = rest.strip()

    # Split the level description into lines, remove trailing and leading
    # whitespaces, and remove empty lines
    lines = filter(None, [x.strip() for x in level.strip().split('\n')])

    # Child format defined in the first line
    # Format: var_name1/var_name2/.../var_nameN
    var_names = [x.strip() for x in lines[0].split('/')]

    # Evaluate variables in specified order, don't shuffle them!
    var_formats = []

    # List of children tuples
    children = []

    # Skip first line!
    for x in lines[1:]:
        left, separator, right = x.partition('=')

        if separator:
            # Variable definition: var_name=this is a example number {x}
            var_formats.append((left, right))
        elif left[0] == '%':
            # Special command
            if left.startswith('%RANGE'):
                # E.g. %RANGE 2012, 1996
                # --> Adds children: 2012, 2011, ..., 1997, 1996
                a, b = [int(x) for x in left[6:].split(',')]
                r = range(a, b + 1) if a <= b else range(a, b - 1, -1)
                children.extend([str(x) for x in r])
            else:
                raise Exception('Nepoznata naredba: ' + left)
        else:
            # Child definition: var_value1/var_value2/.../var_valueN
            children.append(left)

    # Total number of created folders.
    total = 0
    for index, x in enumerate(children):
        # Update vars with child var values. (values are stripped!)
        vars.update({k: v.strip() for k, v in zip(var_names, x.split('/'))})

        # Update additional vars
        for var in var_formats:
            # Note we are using same dictionary that is being updated, that's
            # why order matters
            vars[var[0]] = var[1].format(**vars)

        # Create new folder
        folder = Folder(author=author, parent=parent, parent_index=index,
            hidden=False, editable=False, name=vars['name'],
            short_name=vars['short'], tag_filter=vars['tags'],
            slug=slugify(vars['short']))
        folder.save()

        total += 1

        # Call recursion if there is any level left
        if rest:
            # Note that parent changed!
            total += _create_folders(author, folder, rest, _dict_to_object(vars))

    return total

# stored as object_repr in django_admin_log
ADVANCED_NEW_OBJECT_REPR = u'<advanced new>'

@permission_required('folder.advanced_create')
@response('folder_advanced_new.html')
def advanced_new(request):
    """
        Create folders defined by structure and the parent.

        Structure format:
            level1 [ | level2 [ | level3 ... ] ]
        Level format:
            i) variable names
            ii) list of child folders - variable values
            iii) format of additional variables

        Or, more detailed:
            var_name1/var_name2/...var_nameN

            child1_var_value1/child1_var_value2/.../child1_var_valueN
            ...
            childM_var_value1/childM_var_value2/.../childM_var_valueN

            some_var={var_nameX} some text, {var_nameX}
            other_var={var_nameY} {var_nameZ} text text

        Also, to access variables from previous levels, use 'p.' prefix. E.g:
            name={p.competition_name} {year}

        There are three variables that has to be set (as i+ii or iii):
            name = full name of the folder
            short = shown in menu
            tags = tag filters for the folder
        If any of these variables are missing, parser will throw an expection.

        Special functions:
            Instead of listing dozens of years (ii part), you can use this
            helper function:
                %RANGE a, b
            which acts like numbers from a to b, inclusive (works both asc/desc)



        Real example:
            name/tags

            International Mathematical Olympiad/imo
            International Mathematical Olympiad - Shortlist/shortlist

            short={name}

            |

            year

            %RANGE 2011, 1959

            name={p.name} {year}
            short={year}
            tags={p.tags},{year}
    """

    content_type = ContentType.objects.get_for_model(Folder)

    total = 0
    if request.POST:
        form = FolderAdvancedCreateForm(request.user, request.POST)
        if form.is_valid():
            parent = form.cleaned_data['parent']
            structure = form.cleaned_data['structure']

            # Use admin log to save structure for future changes
            LogEntry.objects.log_action(user_id=request.user.id,
                content_type_id=content_type.id, object_id=parent.id,
                object_repr=ADVANCED_NEW_OBJECT_REPR, action_flag=CHANGE,
                change_message=structure)

            print 'Creating folders...'
            total = _create_folders(request.user, parent, structure, None)

            print 'Refreshing folder cache...'
            refresh_cache(Folder.objects.all())

    else:
        form = FolderAdvancedCreateForm(request.user)

    structure_history = LogEntry.objects.filter(content_type=content_type,
        object_repr=ADVANCED_NEW_OBJECT_REPR)
    history_array = [x.change_message for x in structure_history];

    return {
        'form': form,
        'new_folder_count': total,
        'structure_history': structure_history,
        'history_array': history_array,
    }
