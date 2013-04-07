﻿from django import forms
from django.conf import settings
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Min
from django.http import Http404, HttpResponse, HttpResponseRedirect, HttpResponseServerError
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext

from pagination.paginator import InfinitePaginator
from taggit.utils import parse_tags

from task.models import Task, SimilarTask
from task.forms import TaskForm, TaskAdvancedForm, TaskExportForm, EXPORT_FORMAT_CHOICES

from activity import action as _action
from folder.models import Folder
from folder.utils import get_folder_template_data
from permissions.constants import EDIT, VIEW, EDIT_PERMISSIONS
from permissions.models import ObjectPermission
from recommend.utils import task_event
from search.utils import update_search_cache
from solution.models import Solution, STATUS as _SOLUTION_STATUS
from solution.views import get_user_solved_tasks
from mathcontent.forms import MathContentForm
from mathcontent import latex
from mathcontent.models import MathContent, Attachment
from usergroup.forms import GroupEntryForm

from skoljka.utils import get_referrer_path
from skoljka.utils.decorators import response
from skoljka.utils.timeout import run_command

import os, sys, hashlib, codecs, datetime, zipfile

# TODO: promijeniti nacin na koji se Task i MathContent generiraju.
# vrijednosti koje ne ovise o samom formatu se direktno trebaju
# postaviti na vrijednosti iz forme

@transaction.commit_on_success
@permission_required('task.add_advanced')
def advanced_new(request):
    """
        Used only by admin
    """

    if request.method == 'POST':
        task_form = TaskAdvancedForm(request.POST)
        math_content_form = MathContentForm(request.POST)
        group_form = GroupEntryForm(request.POST)

        if task_form.is_valid() and math_content_form.is_valid() and group_form.is_valid():
            task_template = task_form.save(commit=False)
            math_content_template = math_content_form.save(commit=False)

            groups = group_form.cleaned_data['list']

            from collections import defaultdict
            dictionary = defaultdict(unicode)

            from xml.dom.minidom import parseString
            from xml.dom.minidom import Node
            dom = parseString(math_content_template.text.encode('utf-8'))
            # Xml -> <info> ... </info>

            for x in dom.firstChild.childNodes:
                if x.nodeType == Node.TEXT_NODE:
                    continue

                if x.nodeName != 'content':
                    if x.nodeValue:
                        value = x.nodeValue
                    elif x.firstChild and x.firstChild.nodeValue:
                        value = x.firstChild.nodeValue
                    else:
                        value = ''
                    dictionary[x.nodeName] = value
                    print (u'Postavljam varijablu "%s" na "%s"' % (x.nodeName, value)).encode('utf-8')

                if x.nodeName == 'content':
                    print (u'Dodajem zadatak "%s" s tagovima "%s"' % (task_template.name % dictionary, task_form.cleaned_data['_tags'] % dictionary)).encode('utf-8')
                    value = x.nodeValue or ''
                    if x.firstChild:
                        value += x.firstChild.nodeValue or ''
                    math_content = MathContent()
                    math_content.text = value     # should be safe
                    math_content.save()
                    print 'uspio dodati math_content'

                    # rucno spajam 'tags1' i 'tags'
                    if 'tags1' in dictionary:
                        dictionary['tags'] = dictionary.get('tags', '') + ',' + dictionary['tags1']
                        dictionary.pop('tags1')     # samo za ovaj zadatak!

                    task = Task()
                    task.name = task_template.name % dictionary
                    task.author = request.user
                    task.content = math_content
# TODO: automatizirati .hidden (vidi TODO na vrhu funkcije)
                    task.hidden = task_template.hidden
                    task.source = task_template.source % dictionary
                    task.save()

                    # WARNING: .set is case-sensitive!
                    tags = parse_tags(task_form.cleaned_data['_tags'] % dictionary)
                    task.tags.set(*tags)
                    update_search_cache(task, [], tags)

                    # --- difficulty ---
                    difficulty = task_form.cleaned_data['_difficulty'] % dictionary
                    if difficulty:
                        task.difficulty_rating.update(request.user, int(difficulty))

                    # --- group permissions ---
                    for x in groups:
                        ObjectPermission.objects.create(content_object=task, group=x, permission_type=VIEW)
                        ObjectPermission.objects.create(content_object=task, group=x, permission_type=EDIT)


            return HttpResponseRedirect('/task/new/finish/')
    else:
        task_form = TaskAdvancedForm()
        group_form = GroupEntryForm()
        math_content_form = MathContentForm()

    return render_to_response( 'task_new.html', {
                'forms': [task_form, group_form, math_content_form],
                'action_url': request.path,
                'advanced': True,
            }, context_instance=RequestContext(request),
        )

################################################
# ovo je stara verzija, sa starim formatom

# TODO: maknuti debug s vremenom
def _advanced_new_parse(s, dictionary):
    print 'primio', s
    s = s % dictionary
    print 'vracam', s
    return s

@permission_required('task.add_advanced')
def old_advanced_new(request):
    if request.method == 'POST':
        task_form = TaskAdvancedForm(request.POST)
        math_content_form = MathContentForm(request.POST)

        if task_form.is_valid() and math_content_form.is_valid():
            task_template = task_form.save(commit=False)
            math_content_template = math_content_form.save(commit=False)

            contents = math_content_template.text.split('@@@@@')
            contents = [x.strip() for x in contents]

            dictionary = dict()

            print contents
            print len(contents)
            for k in xrange(len(contents)):
                print 'k=%d' % k
                content = contents[k].strip()
                new_vars = content.find('###')
                if new_vars != -1:
                    for key, var in [x.split('=') for x in content[:new_vars].split('|')]:
                        dictionary[key.strip()] = var
                        print u'Postavljam varijablu "%s" na "%s"' % (key.strip(), var)
                    content = content[new_vars + 3:].strip()

                if not content:     # skip empty tasks
                    continue

                math_content = MathContent()
                math_content.text = content
                math_content.save()
                print 'uspio dodati math_content'

                task = Task()
                task.name = _advanced_new_parse(task_template.name, dictionary)
                task.author = request.user
                task.content = math_content
# TODO: automatizirati .hidden: (vidi TODO na vrhu funkcije)
                task.hidden = task_template.hidden
                task.save()

                tags = parse_tags(_advanced_new_parse(task_form.cleaned_data['_tags'], dictionary))
                task.tags.set(*tags)
                update_search_cache(task, [], tags)

            return HttpResponseRedirect('/task/new/finish/')
    else:
        task_form = TaskAdvancedForm()
        math_content_form = MathContentForm()

    return render_to_response( 'task_new.html', {
                'forms': [task_form, math_content_form],
                'action_url': request.path,
                'advanced': True,
            }, context_instance=RequestContext(request),
        )

# kraj starog koda
#########################################################

@login_required
@response('task_new.html')
def new(request, task_id=None):
    """
        New Task and Edit Task
    """
    if task_id:
        task = get_object_or_404(Task, pk=task_id)
        math_content = task.content
        old_tags = list(task.tags.values_list('name', flat=True))
        edit = True
        if not task.user_has_perm(request.user, EDIT):
            return 403
    else:
        task = math_content = None
        old_tags = []
        edit = False

    if request.method == 'POST':
        print request.POST
        task_form = TaskForm(request.POST, instance=task, user=request.user)
        math_content_form = MathContentForm(request.POST, instance=math_content)

        if task_form.is_valid() and math_content_form.is_valid():
            task = task_form.save(commit=False)
            math_content = math_content_form.save()

            if not edit:
                task.author = request.user

            task.content = math_content
            task.save()

            # Required for django-taggit:
            task_form.save_m2m()
            update_search_cache(task, old_tags, task.tags.values_list('name', flat=True))

            # send action if creating a new nonhidden task
            if not edit and not task.hidden:
                _action.add(request.user, _action.TASK_ADD,
                    action_object=task, target=task)

            # TODO: izbrisati task_new_finish.html i url
            #return HttpResponseRedirect('/task/%d/' % task.id if edit else '/task/new/finish/')
            return HttpResponseRedirect(task.get_absolute_url())
    else:
        task_form = TaskForm(instance=task)
        math_content_form = MathContentForm(instance=math_content)

    return {
        'forms': [task_form, math_content_form],
        'action_url': request.path,
        'edit': edit,
        'task': task,
    }

@response('task_list.html')
def task_list(request, user_id=None):
    tasks = Task.objects.for_user(request.user, VIEW).select_related('content').distinct()
    # treba mi LEFT JOIN ON (task_task.id = solution_solution.task_id AND solution_solution.author_id = ##)
    # sada se umjesto toga koristi .cache_task_info()
    # (slicno za tag-ove)

    if user_id:
        tasks = tasks.filter(author_id=user_id)

    return {
        'tasks' : tasks,
        'submitted_tasks' : get_user_solved_tasks(request.user),
    }

@response('task_detail.html')
def detail(request, id):
    task = get_object_or_404(Task, id=id)
    content_type = ContentType.objects.get_for_model(Task)

    try:
        solution = request.user.is_authenticated() \
            and Solution.objects.get(author=request.user, task=task)
    except (Solution.DoesNotExist, IndexError):
        solution = None

    perm = task.get_user_permissions(request.user)

    if VIEW not in perm:
        return (response.FORBIDDEN, 'Not allowed to view this task!')

    # ovo ce ici preko C++ skripte za pocetak
    # task.update_similar_tasks(1)

    # used for recommendation system and similar
    if request.user.is_authenticated():
        task_event(request.user, task, 'view')

    referrer = get_referrer_path(request)
    folder_data = referrer and get_folder_template_data(referrer, request.user,
        Folder.DATA_MENU)

    return {
        'task': task,
        'can_edit': EDIT in perm,
        'can_edit_permissions': EDIT_PERMISSIONS in perm,
        'content_type': content_type,
        'solution': solution,
        'menu_folder_tree': folder_data['menu_folder_tree'],
    }

@response('task_similar.html')
def similar(request, id):
    task = get_object_or_404(Task, pk=id)

    # TODO: dovrsiti, ovo je samo tmp
    # task.update_similar_tasks(1)
    if request.user.is_authenticated():
        task_event(request.user, task, 'view')

    # SPEED: read main task together with the rest
    # no need to sort here
    similar = list(SimilarTask.objects.filter(task=task)[:50].values_list('similar_id', 'score'))
    if request.user.is_authenticated():
        solutions = Solution.objects.filter(task__similar_backward=task, author=request.user).exclude(status=_SOLUTION_STATUS['blank'])
        solutions = solutions.only('status', 'correctness_avg', 'task')
    else:
        solutions = []

    sorted_tasks = dict(similar)
    for s in solutions:
        p = 1.0
        if s.is_todo(): p = 0.5
        elif s.is_as_solved(): p = 0.3
        elif s.is_submitted():
            if s.is_correct(): p = 0.2

        sorted_tasks[s.task_id] *= p

    # sort here
    sorted_tasks = sorted([(p, id) for id, p in sorted_tasks.iteritems()], reverse=True)
    similar_ids = [id for p, id in sorted_tasks[:6]]

    similar = Task.objects.filter(id__in=similar_ids).select_related('content')

    return {
        'task': task,
        'similar': similar,
        'view_type': 'similar_task_view_type',
    }

# final filename is 'attachments/task_id/attachment index/filename.ext'
ZIP_ATTACHMENT_DIR = 'attachments'

def _convert_to_latex(tasks, has_title, has_url, has_source, has_index, has_id, *args, **kwargs):
    """
        Attachments go to attachments/task_id/attachment_index/filename.ext.
    """
    is_latex = kwargs['format'] == 'latex'

    content = [latex.export_header]
    for k, x in enumerate(tasks):
        # DRY?
        export_title = latex.export_title % x.name if has_title else ''
        export_url = latex.export_url % x.get_absolute_url() if has_url else ''
        export_source = latex.export_source % ('\\textbf{Izvor:} ' + x.source if x.source else '') if has_source else ''
        export_index = latex.export_index % (k + 1) if has_index else ''
        export_id = ('(%d)' % x.id if has_index else '%d.' % x.id) if has_id else ''

        # no / at the end
        attachment_path = is_latex and '{}/{}'.format(ZIP_ATTACHMENT_DIR, x.id)

        content.append(latex.export_task % {
            'export_title': export_title,
            'export_url': export_url,
            'export_source': export_source,
            'export_index': export_index,
            'export_id': export_id,
            'content': x.content.convert_to_latex(
                attachment_path=attachment_path),
        })
    content.append(latex.export_footer)

    return u''.join(content)

def _export(ids, tasks, form):
    """
        Output LaTeX or PDF, permission already checked.
        It is assumed that Attachments are already saved in tasks[...] as
        .cache_file_list
    """
    format = form.cleaned_data['format']

    if format not in ['latex', 'pdf']:
        return (400, 'Export format not valid')

    # Please note that .tex created for .pdf is not the same as .tex for
    # exporting (e.g. there are differences in the attachment path).
    # Those two cases will be distinguished by different hashes.
    hash = hashlib.md5(repr((ids, form.cleaned_data))).hexdigest()

    create_archive = form.cleaned_data['create_archive']
    filename = os.path.normpath(os.path.join(settings.LOCAL_DIR,
        'media/export/task' + hash))    # no extension

    # check if output already exists
    ext = '.pdf' if format == 'pdf' else '.tex'
    fext = '.zip' if create_archive else ext         # final ext

    # TODO: check if archive exists (currently, it is not trivially possible
    # to check if there were some changes to attachments)
    if not create_archive and os.path.exists(filename + fext):
        oldest_file_mtime = tasks.aggregate(Min('last_edit_date'))['last_edit_date__min']
        if datetime.datetime.fromtimestamp(os.path.getmtime(filename + fext)) > oldest_file_mtime:
            # already up-to-date
            return HttpResponseRedirect('/media/export/task{}{}'.format(hash, fext))

    latex = _convert_to_latex(tasks, **form.cleaned_data)

    # if latex without archive, do not create file, but directly output it
    if format == 'latex' and not create_archive:
        response = HttpResponse(content=latex, content_type='application/x-latex')
        response['Content-Disposition'] = 'filename=taskexport.tex'
        return response

    # otherwise, save generated latex into a file
    f = codecs.open(filename + '.tex', 'w', encoding='utf-8')
    f.write(latex)
    f.close()

    if format == 'pdf':
        error = run_command('pdflatex -output-directory=%s -interaction=batchmode %s.tex' \
            % (os.path.dirname(filename), filename), timeout=10)
        if error:
            return HttpResponseServerError('LaTeX generation error! Error code: %d' % error)

        # error = run_command('dvipdfm -o %s %s' % (filename + '.pdf', filename), timeout=10)
        # if error:
            # return HttpResponseServerError('dvipdfm Error %d!' % error)
        # os.remove(filename + '.tex')
        # os.remove(filename + '.log')
        # os.remove(filename + '.aux')
        # os.remove(filename + '.dvi')

    if create_archive:
        f = zipfile.ZipFile(filename + '.zip', mode='w',
            compression=zipfile.ZIP_DEFLATED)

        f.write(filename + ext, 'task{}{}'.format(hash, ext))
        for task in tasks:
            for k in range(len(task.cache_file_list)):
                attachment = task.cache_file_list[k]
                f.write(attachment.file.name, '{}/{}/{}/{}'.format(
                    ZIP_ATTACHMENT_DIR, task.id, k, attachment.get_filename()))

        f.close()

    return HttpResponseRedirect('/media/export/task{}{}'.format(hash, fext))

@response('task_export.html')
def export(request, format=None, ids=None):
    """
        Exports tasks with given ids to given format.
        Format and ids can be given as GET or POST information.
    """

    # Please note that both TaskExportForm and unnamed form (format, ids)
    # use POST method. To prevent collision, submit button in TaskExportForm
    # is named 'action'.

    POST = request.POST.copy()

    # Move URL / GET data to POST
    if format and ids:
        POST['format'] = format
        POST['ids'] = ids
    else:
        format = POST.get('format')
        ids  = POST.get('ids')

    print POST

    available_formats = dict(EXPORT_FORMAT_CHOICES)
    if not ids or format not in available_formats:
        raise Http404

    try:
        id_list = [int(x) for x in ids.split(',')]
    except ValueError:
        raise Http404

    # check for permissions
    tasks = Task.objects.for_user(request.user, VIEW).filter(id__in=id_list).select_related('content').distinct()
    if len(tasks) != len(id_list):
        raise Http404('Neki od navedenih zadataka ne postoje ili su sakriveni.')

    # permission ok, use shortened query
    tasks = Task.objects.filter(id__in=id_list)

    # force queryset evaluation and prepare all attachments...
    content_to_task = {}
    for task in tasks:
        task.cache_file_list = []
        content_to_task[task.content_id] = task

    # attachments
    query = "SELECT A.* FROM mathcontent_attachment A"                  \
            " INNER JOIN task_task B ON A.content_id = B.content_id"    \
            " WHERE B.id IN ({})".format(ids)
    attachments = list(Attachment.objects.raw(query))
    for attachment in attachments:
        content_to_task[attachment.content_id].cache_file_list.append(attachment)

    if request.method == 'POST' and 'action' in POST:
        form = TaskExportForm(POST)
        if form.is_valid():
            # note that attachments are imported into each task as .cache_file_list
            return _export(ids, tasks, form)

    # otherwise, if form not given or not valid:

    create_archive = len(attachments) > 0
    if len(id_list) == 1:
        data = (format, ids, True, True, True, False, False, create_archive)
    else:
        data = (format, ids, False, False, False, False, True, create_archive)

    data = dict(zip(('format', 'ids', 'has_title', 'has_url', 'has_source',
        'has_index', 'has_id', 'create_archive'), data))
    form = TaskExportForm(data)

    if len(attachments):
        form.fields['create_archive'].label = \
            'Zip arhiva (ukupno datoteka: {}+1)'.format(len(attachments))
    else:
        form.fields['create_archive'].widget = forms.HiddenInput()

    return {
        'format': available_formats[format],
        'form': form,
        'tasks': tasks,
        'attachments': attachments,
    }
