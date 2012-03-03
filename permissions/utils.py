from django.contrib.contenttypes.models import ContentType

#from permissions.models import PerObjectUserPermission
from permissions.models import PerObjectGroupPermission

# # don't waste time making values unique
def get_permissions_for_object_by_id(user, object_id, content_type):
    if not user.is_authenticated():
        return []
#    return [x for x in PerObjectUserPermission.objects.filter(
#                    object_id=object_id, content_type=content_type, user=user
#                ).values_list('permission_type', flat=True)]           \
    return [x for x in PerObjectGroupPermission.objects.filter(
                    object_id=object_id, content_type=content_type, group__user=user
                ).values_list('permission_type', flat=True)]

def get_permissions_for_object(user, obj):
    content_type = ContentType.objects.get_for_model(obj)
    return get_permissions_for_object_by_id(user, obj.id, content_type)
