import datetime
import json

from django.contrib.auth.models import Group, User
from django.http import HttpResponse, HttpResponseBadRequest
from django.template.defaultfilters import capfirst
from django.views.decorators.csrf import csrf_exempt

from skoljka.competition.models import (
    Chain,
    ChainTeam,
    Competition,
    CompetitionTask,
    Team,
    TeamMember,
)
from skoljka.competition.utils import create_ctask
from skoljka.mathcontent.models import MathContent
from skoljka.permissions.constants import EDIT, VIEW
from skoljka.permissions.models import ObjectPermission
from skoljka.usergroup.models import UserGroup
from skoljka.usergroup.utils import add_users_to_group
from skoljka.userprofile.models import create_user_profile
from skoljka.utils.testutils import assert_testdb

TEST_COMPETITION_URLS = {
    10001: 'public_competition',
    10002: 'hidden_competition',
    10003: 'competition_with_categories',
    10004: 'individual_competition_with_categories',
    10005: 'individual_competition_without_categories',
    10006: 'individual_competition_with_nonconfigurable_categories',
    10007: 'individual_course_without_categories',
    10008: 'competition_with_no_url_path_prefix',
    10009: 'course_with_no_url_path_prefix',
    10010: 'competition_with_default_max_submissions_2',
}
_COMPETITION_URL_TO_ID = {url: id for id, url in TEST_COMPETITION_URLS.items()}

TEST_USER_PASSWORD = 'a'


def create_competition(moderators, url, **kwargs):
    """Create an empty public competition."""
    HOUR = datetime.timedelta(hours=1)
    NOW = datetime.datetime.now()

    # TODO: Use some kind of API for creating a group.
    group = Group.objects.create(name="{}_group".format(url))
    group_description = MathContent.objects.create(text="abcdef")
    UserGroup.objects.create(
        group=group, description=group_description, author=moderators[0]
    )
    add_users_to_group(moderators, group, added_by=None)

    competition = Competition(
        id=_COMPETITION_URL_TO_ID[url],
        name=capfirst(url.replace("_", " ")),
        kind=Competition.KIND_COMPETITION,
        hidden=False,
        admin_group_id=group.id,
        registration_open_date=NOW - 24 * HOUR,
        start_date=NOW - 1 * HOUR,
        scoreboard_freeze_date=NOW - 23 * HOUR,
        end_date=NOW + 24 * HOUR,
        url_path_prefix='/{}/'.format(url),
    )
    for key, value in kwargs.items():
        setattr(competition, key, value)
    competition.save()

    ObjectPermission.objects.create(
        content_object=competition, group=group, permission_type=EDIT
    )
    ObjectPermission.objects.create(
        content_object=competition, group=group, permission_type=VIEW
    )

    return competition


def create_n_users(prefix, n):
    """Create `n` users, with username `prefix + str(i)`, where `i` goes from
    `0` to `n-1`."""
    users = []
    for i in range(n):
        user = User.objects.create(
            username="{}{}".format(prefix, i),
            is_active=True,
            is_superuser=False,
            is_staff=False,
        )
        user.set_password(TEST_USER_PASSWORD)
        user.save()
        create_user_profile(user)
        users.append(user)

    return users


@csrf_exempt
@assert_testdb
def create_test_competitions(request):
    """Fill the database will all default data for testing competitions."""
    TEAM_CATEGORIES = '{"hr": {"1": "Crvena", "2": "Zelena", "3": "Plava"}, "en": {"1": "Red", "2": "Green", "3": "Blue"}}'
    NONCONFIGURABLE_TEAM_CATEGORIES = '{"hr": {"1": "Crvena", "2": "Zelena", "3": "Plava"}, "en": {"1": "Red", "2": "Green", "3": "Blue"}, "CONFIGURABLE": false}'

    moderators = create_n_users("moderator", 5)
    create_n_users("competitor", 10)

    create_competition(moderators, "public_competition")
    create_competition(moderators, "hidden_competition", hidden=True)
    create_competition(
        moderators, "competition_with_categories", team_categories=TEAM_CATEGORIES
    )
    create_competition(
        moderators,
        "individual_competition_with_categories",
        max_team_size=1,
        team_categories=TEAM_CATEGORIES,
    )
    create_competition(
        moderators, "individual_competition_without_categories", max_team_size=1
    )
    create_competition(
        moderators,
        "individual_competition_with_nonconfigurable_categories",
        max_team_size=1,
        team_categories=NONCONFIGURABLE_TEAM_CATEGORIES,
    )
    create_competition(
        moderators,
        "individual_course_without_categories",
        max_team_size=1,
        kind=Competition.KIND_COURSE,
    )
    create_competition(
        moderators,
        "competition_with_no_url_path_prefix",
        url_path_prefix="",
    )
    create_competition(
        moderators,
        "course_with_no_url_path_prefix",
        kind=Competition.KIND_COURSE,
        url_path_prefix="",
    )
    create_competition(
        moderators,
        "competition_with_default_max_submissions_2",
        default_max_submissions=2,
    )

    response = {}
    return HttpResponse(json.dumps(response), mimetype='application/json')


def _create_test_ctasks(request, competition_id, chain=None):
    if not request.user.is_authenticated():
        raise Exception("must be signed in as the ctask author")

    competition = Competition.objects.get(id=competition_id)
    num_tasks = int(request.POST['num-tasks'])
    text_format = request.POST['text-format']
    comment_format = request.POST['comment-format']

    ctask_ids = []
    for i in range(num_tasks):
        # Note: chain_position is for some reason assumed to be 1-based.
        ctask = CompetitionTask(
            competition=competition,
            descriptor=str(100 + i),
            max_submissions=competition.default_max_submissions,
            chain=chain,
            chain_position=(-1 if chain is None else i + 1),
        )
        create_ctask(
            ctask,
            request.user,
            competition,
            text_format.format(i),
            comment_format.format(i),
        )
        ctask_ids.append(ctask.id)

    return ctask_ids


@csrf_exempt
@assert_testdb
def create_test_ctasks(request, competition_id):
    """Create multiple ctasks.

    POST arguments:
        num-tasks: number of ctasks to create
        text-format: .format()-compatible format for the ctask text
        comment-format: .format()-compatible format for the ctask comment

    Returns a JSON:
        {'ctask_ids': [...]}
    """
    ctask_ids = _create_test_ctasks(request, competition_id)
    response = {'ctask_ids': ctask_ids}
    return HttpResponse(json.dumps(response), mimetype='application/json')


@csrf_exempt
@assert_testdb
def create_test_chain(request, competition_id):
    """Create multiple ctasks.

    Chain POST arguments:
        name
        unlock-minutes
        category
        bonus
        position
        unlock-mode

    Ctask POST arguments:
        num-tasks: number of ctasks to create and assign to the chain
        text-format: .format()-compatible format for the ctask text
        comment-format: .format()-compatible format for the ctask comment

    Returns a JSON:
        {'chain_id': chain.id, 'ctask_ids': [...]}
    """
    chain = Chain.objects.create(
        competition_id=competition_id,
        name=request.POST['name'],
        unlock_minutes=request.POST['unlock-minutes'],
        category=request.POST['category'],
        bonus_score=request.POST['bonus'],
        position=request.POST['position'],
        unlock_mode=request.POST['unlock-mode'],
        restricted_access=(request.POST['restricted-access'] == 'true'),
    )
    ctask_ids = _create_test_ctasks(request, competition_id, chain=chain)
    response = {'chain_id': chain.id, 'ctask_ids': ctask_ids}
    return HttpResponse(json.dumps(response), mimetype='application/json')


@csrf_exempt
@assert_testdb
def create_test_team(request, competition_id):
    """Create a team with one or more members. Returns a single number, the team ID."""
    body = json.loads(request.body)
    usernames = body['member-usernames']
    members = list(User.objects.filter(username__in=usernames))
    if len(members) != len(usernames):
        return HttpResponseBadRequest("some usernames do not exist")
    author = next(member for member in members if member.username == usernames[0])
    team = Team.objects.create(
        name=body['name'],
        author=author,
        competition_id=competition_id,
        category=body['category'],
    )
    for member in members:
        TeamMember.objects.create(
            team=team,
            member=member,
            member_name=member.username,
            invitation_status=TeamMember.INVITATION_ACCEPTED,
        )
    for chain_id in body['chain-access']:
        ChainTeam.objects.create(chain_id=chain_id, team=team)

    response = team.id
    return HttpResponse(json.dumps(response), mimetype='application/json')


@csrf_exempt
@assert_testdb
def delete_teams(request, competition_id):
    """Delete teams, given a JSON list of the IDs. Check that the teams exist."""
    team_ids = json.loads(request.body)
    teams = Team.objects.filter(competition_id=competition_id, id__in=team_ids)
    if len(teams) != len(team_ids):
        return HttpResponseBadRequest("some teams don't exist")
    teams.delete()
    return HttpResponse('{}', mimetype='application/json')
