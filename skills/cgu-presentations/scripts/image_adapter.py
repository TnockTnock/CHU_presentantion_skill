"""Aspect-preserving crop with normalized focus; no raster edits."""
import math

def validate(value):
    if value.get('fit','cover') not in ('cover','contain'):raise ValueError('Image fit must be cover or contain')
    focus=value.get('focus',[.5,.5])
    if not isinstance(focus,list) or len(focus)!=2 or any(type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=1 for x in focus):raise ValueError('Image focus requires two finite coordinates in [0,1]')
    if not isinstance(value.get('alt'),str) or not value['alt'].strip():raise ValueError('Image alt required')

def crop(width,height,box_width,box_height,focus=(.5,.5)):
    if min(width,height,box_width,box_height)<=0:raise ValueError('Invalid image dimensions')
    ratio=(box_width/box_height)/(width/height)
    visible_x=min(1,ratio);visible_y=min(1,1/ratio)
    left=min(max(focus[0]-visible_x/2,0),1-visible_x)
    top=min(max(focus[1]-visible_y/2,0),1-visible_y)
    return dict(l=round(left*100000),r=round((1-visible_x-left)*100000),t=round(top*100000),b=round((1-visible_y-top)*100000))
