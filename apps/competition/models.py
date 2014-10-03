from django.contrib.auth.models import User, Group
from django.db import models

from permissions.constants import EDIT
from permissions.models import BasePermissionsModel
from post.generic import PostGenericRelation
from task.models import Task

class Competition(BasePermissionsModel):
    name = models.CharField(max_length=64)
    hidden = models.BooleanField(default=True)
    registration_open_date = models.DateTimeField()
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    default_max_submissions = models.IntegerField(default=3)
    max_team_size = models.IntegerField(default=3)
    admin_group = models.ForeignKey(Group, blank=True, null=True)
    automatic_task_tags = models.CharField(blank=True, max_length=64)
    description_template_filename = models.CharField(blank=True, max_length=255)
    rules_template_filename = models.CharField(blank=True, max_length=255)
    url_path_prefix = models.CharField(blank=True, max_length=64)

    posts = PostGenericRelation(placeholder="Poruka")

    def __unicode__(self):
        return self.name

    def get_absolute_url(self):
        return self.url_path_prefix or '/competition/{}/'.format(self.id)

    def can_send_post(self, user): # PostGenericRelation
        return self.user_has_perm(user, EDIT)



class Team(models.Model):
    name = models.CharField(max_length=40)
    author = models.ForeignKey(User)
    competition = models.ForeignKey(Competition)
    cache_score = models.IntegerField(default=0)
    is_test = models.BooleanField(default=False)

    posts = PostGenericRelation(placeholder="Poruka")

    def __unicode__(self):
        return self.name

    def can_send_post(self, user): # PostGenericRelation
        # Only members and and admins can post messages to team.posts.
        if TeamMember.objects.filter(member=user, team=self).exists():
            return True
        return self.competition.user_has_perm(user, EDIT)



class TeamMember(models.Model):
    team = models.ForeignKey(Team)
    member = models.ForeignKey(User, blank=True, null=True)
    member_name = models.CharField(max_length=64)

    INVITATION_UNANSWERED = 0
    INVITATION_ACCEPTED = 1
    INVITATION_DECLINED = 2
    invitation_status = models.IntegerField(default=INVITATION_UNANSWERED)

    def __unicode__(self):
        return self.team.name + '::' + self.member_name



class Chain(models.Model):
    competition = models.ForeignKey(Competition)
    name = models.CharField(max_length=40)
    unlock_minutes = models.IntegerField(default=0)
    category = models.CharField(blank=True, db_index=True, max_length=32)
    bonus_score = models.IntegerField(default=1)

    def __unicode__(self):
        return self.name

    def get_absolute_url(self):
        return self.competition.get_absolute_url() + 'chain/{}/'.format(self.id)



class CompetitionTask(models.Model):
    class Meta:
        unique_together = (('competition', 'task'), )
    competition = models.ForeignKey(Competition)
    task = models.ForeignKey(Task)
    correct_result = models.CharField(max_length=255)
    max_submissions = models.IntegerField(default=3)
    score = models.IntegerField(default=1)
    chain = models.ForeignKey(Chain)
    chain_position = models.IntegerField(default=0)

    def __unicode__(self):
        return "CompetitionTask #{} comp={} task={}".format(
                self.id, self.competition_id, self.task_id)

    def get_absolute_url(self):
        return self.competition.get_absolute_url() + 'task/{}/'.format(self.id)

    def check_result(self, result):
        return result == self.correct_result



class Submission(models.Model):
    ctask = models.ForeignKey(CompetitionTask)
    team = models.ForeignKey(Team)
    date = models.DateTimeField(auto_now_add=True)
    result = models.CharField(max_length=255)
    cache_is_correct = models.BooleanField()

    def __unicode__(self):
        return "ctask={} team={} {}".format(
                self.ctask_id, self.team_id, self.date)
