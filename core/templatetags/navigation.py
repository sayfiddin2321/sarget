from django import template

register = template.Library()


@register.simple_tag
def page_url(request, number):
    query = request.GET.copy()
    query['page'] = number
    return '?' + query.urlencode()
