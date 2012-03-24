from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group
from django.contrib.contenttypes.models import ContentType
from django.http import Http404, HttpResponseRedirect, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext

from activity import action as _action
from mathcontent.forms import MathContentForm
from permissions.constants import *
from permissions.models import PerObjectGroupPermission
from usergroup.forms import GroupForm, UserGroupForm, UserEntryForm
from usergroup.models import UserGroup, GroupExtended


@login_required
def leave(request, group_id=None):
    group = get_object_or_404(Group.objects.select_related('data'), id=group_id)
    if group.data is None:
        return HttpResponseForbidden('Can\'t leave your private user-group.')
        
    # TODO: ovaj query vjerojatno radi nepotreban JOIN
    is_member = request.user.groups.filter(id=group_id).exists()
    if not is_member:
        return HttpResponseForbidden('You are not member of this group.')
    
    print request.POST
    if request.method == 'POST':
        if request.POST.get('confirm') == u'1':
            request.user.groups.remove(group)
            group.data.member_count = User.groups.through.objects.filter(group=group).count()
            group.data.save(force_update=True)
            _action.send(request.user, _action.GROUP_LEAVE, action_object=request.user, target=group, public=False, group=group)
            return HttpResponseRedirect('/usergroup/')

    return render_to_response('usergroup_leave.html', {
            'group': group,
        }, context_instance=RequestContext(request))

#TODO: optimizirati ako je moguce
@login_required
def detail(request, group_id=None):
    group = get_object_or_404(Group.objects.select_related('data'), id=group_id)
    
    # FIXME: pipkavo
    if group.data is None:
        return HttpResponseRedirect('/profile/%d/' % group.user_set.all()[0].id)

    perm, is_member = group.data.get_permissions_for_user(request.user)

    if VIEW not in perm:
        return HttpResponseForbidden('You are not member of this group, and you cannot view it\'s details.')

    
    return render_to_response('usergroup_detail.html', {
            'group': group,
            'is_member': is_member,
            'can_edit': EDIT in perm,
            'can_add_members': ADD_MEMBERS in perm,
        }, context_instance=RequestContext(request))


# TODO: perm!!
@login_required
def new(request, group_id=None):
    if group_id:
        group = get_object_or_404(Group.objects.select_related('data', 'data__description'), id=group_id)
        if not group.data:
            return HttpResponseBadRequest('You can\'t edit your own private user-group (or there is some data error).')

        usergroup = group.data
        perm, is_member = usergroup.get_permissions_for_user(request.user)
        if EDIT not in perm:
            return HttpResponseForbidden('You do not have permission to edit this group\'s details.')

        description = usergroup.description
        edit = True
    else:
        group = usergroup = description = None
        edit = False
        
    if request.method == 'POST':
        group_form = GroupForm(request.POST, instance=group)
        usergroup_form = UserGroupForm(request.POST, instance=usergroup)
        description_form = MathContentForm(request.POST, instance=description)
        if group_form.is_valid() and usergroup_form.is_valid() and description_form.is_valid():
            group = group_form.save()
            description = description_form.save();
            usergroup = usergroup_form.save(commit=False)
            
            usergroup.group = group
            usergroup.description = description
            usergroup.author = request.user
            usergroup.save()

            if not edit:
                # TODO: napraviti ALL samo za grupe
                author_group = Group.objects.get(name=request.user.username)
                for perm in ALL:
                    author_perm = PerObjectGroupPermission(content_object=group, group=author_group, permission_type=perm)
                    author_perm.save()

                # permissions assigned to whole group (each member)
                # every group member has perm to view it
                for perm in [VIEW]:
                    self_perm = PerObjectGroupPermission(content_object=group, group=group, permission_type=perm)
                    self_perm.save()
            
            return HttpResponseRedirect('/usergroup/%d/' % group.id)
    else:
        group_form = GroupForm(instance=group)
        usergroup_form = UserGroupForm(instance=usergroup)
        description_form = MathContentForm(instance=description)

    return render_to_response('usergroup_new.html', {
            'group': group,
            'edit': edit,
            'new_group': not edit,
            'forms': [group_form, usergroup_form, description_form],
        }, context_instance=RequestContext(request))

        
@login_required
def list(request):
    return render_to_response('usergroup_list.html', {
            'groups': GroupExtended.objects.for_user(request.user, VIEW).select_related('data'),
        }, context_instance=RequestContext(request))


@login_required
def members(request, group_id=None):
    group = get_object_or_404(Group.objects.select_related('data'), id=group_id)
    perm, is_member = group.data.get_permissions_for_user(request.user)
    
    if VIEW not in perm:
        return HttpResponseForbidden('You do not have permission to edit this group\'s details.')

    if ADD_MEMBERS in perm and request.method == 'POST':
        form = UserEntryForm(request.POST)
        if form.is_valid():
            users = form.cleaned_data['list']
            for user in users:
                #user.groups.add(group)
                dummy, created = User.groups.through.objects.get_or_create(user=user, group=group)
                if created:
                    _action.send(request.user, _action.GROUP_ADD, action_object=user, target=group, public=False, group=group)
            group.data.member_count = group.data.get_users().count()
            group.data.save()
            form = UserEntryForm()
    else:
        form = UserEntryForm()   


    return render_to_response('usergroup_members.html', {
            'group': group,
            'form': form,
            'is_member': is_member,
            'can_view_perm': EDIT_PERMISSIONS in perm,
            'can_edit': EDIT in perm,
            'can_add_members': ADD_MEMBERS in perm,
        }, context_instance=RequestContext(request))        
