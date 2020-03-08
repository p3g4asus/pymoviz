from kivy.lang import Builder
from kivy.logger import Logger
from kivymd.uix.list import IRightBodyTouch, OneLineAvatarListItem, OneLineListItem
from kivymd.uix.selectioncontrol import MDCheckbox
from kivy.properties import ObjectProperty, StringProperty

Builder.load_string(
    '''
<BrandItemSimple>:
    on_release: self.dispatch_on_brand(None)
<BrandItemCB>:
    on_release: self.dispatch_on_brand(None)
    BrandCheckbox:
        id: id_cb
        group: root.group
        disabled: root.disabled
        on_active: root.dispatch_on_brand(self, self.active)
    '''
)


class BrandItemSimple(OneLineListItem):
    brandinfo = ObjectProperty()

    def __init__(self, *args, **kwargs):
        self.register_event_type('on_brand')

    def dispatch_on_brand(self, inst, active):
        Logger.debug(f"BrandItem: Dispatching on brand->{str(active)}")
        self.dispatch("on_brand", self.brandinfo, active)

    def brandinfo2gui(self, b):
        self.text = str(b) if not self.text else self.text

    def on_brandinfo(self, inst, v):
        self.brandinfo2gui(v)


class BrandItemCB(OneLineAvatarListItem):
    brandinfo = ObjectProperty()
    group = StringProperty(None, allownone=True)

    def __init__(self, *args, **kwargs):
        self.register_event_type('on_brand')
        if 'active' in kwargs:
            act = kwargs['active']
            del kwargs['active']
        else:
            act = False
        super(BrandItemCB, self).__init__(*args, **kwargs)
        self.set_active(act)

    def brandinfo2gui(self, b):
        self.text = str(b) if not self.text else self.text

    def set_active(self, value):
        self.ids.id_cb.active = value is True

    def get_active(self):
        return self.ids.id_cb.active

    def on_brandinfo(self, inst, v):
        self.brandinfo2gui(v)

    def dispatch_on_brand(self, inst, active):
        Logger.debug(f"BrandItem: Dispatching on brand->{str(active)}")
        self.dispatch("on_brand", self.brandinfo, active)

    def on_brand(self, brandinfo, active):
        Logger.debug(f"BrandItem: On brand {str(brandinfo)}->{active}")


class BrandCheckbox(MDCheckbox, IRightBodyTouch):
    def __init__(self, *args, **kwargs):
        if 'group' in kwargs and not kwargs['group']:
            del kwargs['group']
        super(BrandCheckbox, self).__init__(*args, **kwargs)

    def on_group(self, inst, group):
        # Logger.debug("Mediaset: group = %s %s %s" % (str(group), str(type(inst)), str(type(group))))
        if group and len(group):
            super(BrandCheckbox, self).on_group(self, group)


def get_brand_item(active=None, **kwargs):
    if active is None:
        return BrandItemSimple(**kwargs)
    else:
        return BrandItemCB(active=active, **kwargs)
