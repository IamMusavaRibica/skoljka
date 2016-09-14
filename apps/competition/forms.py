from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.forms.models import BaseModelFormSet, ModelForm
from django.utils.html import mark_safe
from django.utils.translation import ugettext as _, ugettext_lazy

from competition.models import Chain, CompetitionTask, Team, TeamMember
from competition.evaluator import InvalidDescriptor, InvalidSolution
from competition.evaluator import get_evaluator, get_solution_help_text
from competition.utils import comp_url, ctask_comment_class

from skoljka.libs import xss


class CompetitionSolutionForm(forms.Form):
    result = forms.CharField(max_length=255)

    def __init__(self, *args, **kwargs):
        self.descriptor = kwargs.pop('descriptor')
        self.evaluator = kwargs.pop('evaluator')
        super(CompetitionSolutionForm, self).__init__(*args, **kwargs)

    def clean_result(self):
        data = self.cleaned_data['result']
        try:
            self.evaluator.check_result(self.descriptor, data)
        except InvalidSolution as e:
            # TODO: Make a base form that automatically does this (depending on
            # a parameter).
            self.fields['result'].widget.attrs.update({
                            'class': 'ctask-submit-error'})
            raise forms.ValidationError(unicode(e))
        except InvalidDescriptor as e:
            self.fields['result'].widget.attrs.update({
                            'class': 'ctask-submit-error'})
            raise forms.ValidationError(
                    _("Descriptor error. Please notify admins!"))
        return data



class BaseCompetitionTaskFormSet(BaseModelFormSet):
    def add_fields(self, form, index):
        super(BaseCompetitionTaskFormSet, self).add_fields(form, index)
        # initial_text = form.instance.pk and form.instance.task.content.text
        # form.fields["text"] = forms.CharField(widget=forms.Textarea,
        #         initial=initial_text)



class CompetitionTaskForm(ModelForm):
    text = forms.CharField(widget=forms.Textarea)
    comment = forms.CharField(widget=forms.Textarea, required=False)

    def __init__(self, *args, **kwargs):
        self.competition = kwargs.pop('competition')
        self.evaluator = get_evaluator(self.competition.evaluator_version)
        self.fixed_score = self.competition.fixed_task_score
        user = kwargs.pop('user')
        super(CompetitionTaskForm, self).__init__(*args, **kwargs)

        self.t_comment_extra_class = "ctask-comment"
        if self.instance.pk:
            self.fields['text'].initial = self.instance.task.content.text
            self.fields['comment'].initial = self.instance.comment.text
            self.t_comment_extra_class += \
                    " " + ctask_comment_class(self.instance, user)

        self.fields['descriptor'].help_text = get_solution_help_text(
                self.evaluator, self.initial.get('descriptor'),
                error_message=_("Invalid!"), show_types=True)
        self.fields['descriptor'].label = mark_safe(
                xss.escape(_("Result")) + \
                ' <a href="' + comp_url(self.competition, 'rules') +
                '" target="_blank"><i class="icon-question-sign" title="' +
                xss.escape(_("Help")) + '"></i></a>')
        if self.fixed_score:
            del self.fields['score']

        self.fields['text'].widget.attrs.update(
                {'class': 'comp-mathcontent-text', 'rows': 5})
        self.fields['comment'].widget.attrs.update(
                {'class': 'comp-mathcontent-text ctask-comment', 'rows': 3})

    def clean(self):
        super(CompetitionTaskForm, self).clean()
        self.instance._text = self.cleaned_data.get('text')
        self.instance._comment = self.cleaned_data.get('comment')
        if self.fixed_score:
            self.instance.score = self.fixed_score
        return self.cleaned_data

    def clean_descriptor(self):
        data = self.cleaned_data['descriptor']
        try:
            variables = self.evaluator.parse_descriptor(data)
        except InvalidDescriptor as e:
            self.fields['descriptor'].help_text = ""
            raise forms.ValidationError(unicode(e))
        self.fields['descriptor'].help_text = variables[0].help_text()
        return data

    class Meta:
        model = CompetitionTask
        fields = ('descriptor', 'score')



class ChainForm(forms.ModelForm):
    class Meta:
        model = Chain
        fields = ['name', 'category', 'unlock_minutes', 'bonus_score']



def clean_unused_ctask_ids(competition, ctask_ids):
    if not ctask_ids:
        return [], []
    try:
        ctask_ids = [int(x) for x in ctask_ids.split(',')]
    except ValueError:
        raise ValidationError("Invalid input.")
    ctasks_dict = CompetitionTask.objects \
            .filter(competition=competition).in_bulk(ctask_ids)
    if len(ctask_ids) != len(ctasks_dict):
        raise ValidationError("Unknown competition task ID.")
    for ctask in ctasks_dict.itervalues():
        if ctask.chain_id is not None:
            raise ValidationError("Some tasks were already used.")
    ctasks = [ctasks_dict[id] for id in ctask_ids]
    return ctask_ids, ctasks



class ChainTasksForm(forms.ModelForm):
    ctask_ids = forms.CharField(widget=forms.HiddenInput(), required=False)

    def __init__(self, *args, **kwargs):
        competition = kwargs.pop('competition')
        super(ChainTasksForm, self).__init__(*args, **kwargs)
        self.competition = competition

        self.fields['name'].widget.attrs.update({'class': 'span6'})
        self.fields['category'].widget.attrs.update({'class': 'span2'})
        self.fields['unlock_minutes'].widget.attrs.update({'class': 'span1'})
        self.fields['bonus_score'].widget.attrs.update({'class': 'span1'})
        self.fields['ctask_ids'].widget.attrs.update(
                {'id': 'cchain-unused-ctasks-ids'})

    def clean_ctask_ids(self):
        ctask_ids, ctasks = clean_unused_ctask_ids(
                self.competition, self.cleaned_data['ctask_ids'])
        self.cleaned_data['ctasks'] = ctasks
        return ctask_ids

    class Meta:
        model = Chain
        fields = ['name', 'category', 'unlock_minutes', 'bonus_score']



class TeamForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        instance = kwargs.get('instance', None)
        initial = kwargs.pop('initial', {})
        extra_fields = []
        self.max_team_size = kwargs.pop('max_team_size', 3)
        self.competition_id = kwargs.pop('competition').id

        if instance:
            # Author cannot be removed from the team.
            team_members = list(TeamMember.objects.filter(team=instance) \
                    .exclude(member_id=instance.author_id) \
                    .values_list('member_name', 'member_id'))
        else:
            team_members = []

        # Add extra fields for other members
        for k in xrange(2, self.max_team_size + 1):
            label = u'{}. \u010dlan'.format(k)
            if k - 2 < len(team_members):
                username, user_id = team_members[k - 2]
            else:
                username = user_id = ''
            key = 'member{}_manual'.format(k)
            key_id = 'member{}_user_id'.format(k)
            initial[key] = username
            initial[key_id] = user_id

            extra_fields.append((key, forms.CharField(required=False,
                label=label, max_length=64)))
            extra_fields.append((key_id, forms.CharField(required=False,
                    max_length=32, widget=forms.HiddenInput())))

        super(TeamForm, self).__init__(initial=initial, *args, **kwargs)

        # Preserve order
        for key, value in extra_fields:
            self.fields[key] = value

        self.fields['name'].widget.attrs['class'] = 'span3'
        self.fields['name'].error_messages['required'] = \
                u"Ime tima ne mo\u017ee biti prazno."


    def _clean_member(self, index):
        manual = self.cleaned_data.get('member{}_manual'.format(index))
        user_id = self.cleaned_data.get('member{}_user_id'.format(index))

        if user_id:
            user = User.objects.get(id=user_id)
            return (user.username, user)
        if manual and manual.strip():
            return (manual.strip(), None)
        return None

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if Team.objects \
                .filter(competition_id=self.competition_id, name__iexact=name) \
                .exclude(id=self.instance.id).exists():
            raise ValidationError(
                    u"Uneseno ime tima ve\u0107 iskori\u0161teno!")
        return name

    def clean(self):
        members = []
        ids = set()
        for k in xrange(2, self.max_team_size + 1):
            member = self._clean_member(k)
            if not member:
                continue
            if isinstance(member[1], User):
                if member[1].id not in ids:
                    ids.add(member[1].id)
                    members.append(member)
            else:
                members.append(member)

        self._members = members

        return self.cleaned_data

    class Meta:
        model = Team
        fields = ['name']



class TaskListAdminPanelForm(forms.Form):
    filter_by_team_type = forms.ChoiceField([
        (Team.TYPE_NORMAL, "Natjecatelji"),
        (Team.TYPE_UNOFFICIAL, ugettext_lazy("Unofficial")),
        (Team.TYPE_ADMIN_PRIVATE, "Administratori"),
    ])
    filter_by_status = forms.ChoiceField([
        ('S', "Solved"), ('F', "Failed"), ('T', "Tried")])
