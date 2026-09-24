"""Small read-only TrueType advance reader for the three bundled static Golos fonts."""
import struct
from pathlib import Path
from number_typography import NUMBER

class Font:
    def __init__(self, path):
        self.data=Path(path).read_bytes(); d=self.data
        u16=lambda pos:struct.unpack_from('>H',d,pos)[0]
        u32=lambda pos:struct.unpack_from('>I',d,pos)[0]
        tables={d[12+i*16:16+i*16].decode():u32(20+i*16) for i in range(u16(4))}
        self.units=u16(tables['head']+18)
        self.widths=[u16(tables['hmtx']+4*i) for i in range(u16(tables['hhea']+34))]
        cmap=tables['cmap']; self.glyphs={}
        offsets=[cmap+u32(cmap+8+i*8) for i in range(u16(cmap+2))]
        for off in offsets:
            if u16(off)==4:
                n=u16(off+6)//2;end=off+14;start=end+2*n+2;delta=start+2*n;ranges=delta+2*n
                for i in range(n):
                    lo,hi=u16(start+2*i),u16(end+2*i);shift=u16(delta+2*i);ro=u16(ranges+2*i)
                    for c in range(lo,min(hi,65534)+1):
                        gid=u16(ranges+2*i+ro+2*(c-lo)) if ro else c
                        self.glyphs[c]=(gid+shift)&65535 if gid else 0
                break
        if not self.glyphs:raise ValueError('Bundled font needs Unicode cmap format 4')
    def width(self,text,px):
        total=0
        for c in text:
            gid=self.glyphs.get(ord(c),0)
            if gid==0 and not c.isspace():raise ValueError('Golos has no glyph for '+repr(c))
            total+=self.widths[min(gid,len(self.widths)-1)]
        return total/self.units*px

class Metrics:
    def __init__(self, skill):
        self.fonts={weight:Font(skill/'assets/fonts'/name) for weight,name in [(400,'GolosText_400Regular.ttf'),(600,'GolosText_600SemiBold.ttf'),(700,'GolosText_700Bold.ttf')]}
    def width(self,text,pt,heading):
        total=0;pos=0
        for m in NUMBER.finditer(text):
            total+=self.fonts[600 if heading else 400].width(text[pos:m.start()],pt*4/3)
            total+=self.fonts[700].width(m.group(),pt*4/3);pos=m.end()
        return total+self.fonts[600 if heading else 400].width(text[pos:],pt*4/3)
    def check(self,text,w,h,pt,heading,name):
        lines=0
        for paragraph in text.split('\n'):
            line=''
            for word in paragraph.split():
                if self.width(word,pt,heading)>w:raise ValueError(name+': word wider than text box')
                candidate=line+' '+word if line else word
                if line and self.width(candidate,pt,heading)>w:lines+=1;line=word
                else:line=candidate
            lines+=1
        if lines*pt*4/3*1.18>h+4:raise ValueError(name+': text overflows; shorten or split it')
