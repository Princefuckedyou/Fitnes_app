import sqlite3
import datetime
import calendar as pycalendar
import math
import colorsys
import random

from kivy.app import App
from kivy.animation import Animation
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.image import Image
from kivy.graphics import Color, Rectangle, Line, Ellipse, RoundedRectangle, Triangle, PushMatrix, PopMatrix, Rotate
from kivy.uix.carousel import Carousel
from kivy.clock import Clock
from kivy.uix.slider import Slider
from kivy.properties import ListProperty, NumericProperty, StringProperty
from kivy.utils import get_color_from_hex
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior, DragBehavior
from kivy.uix.modalview import ModalView
from kivy.uix.widget import Widget
from kivy.core.window import Window

# ---------------- 1. БАЗА ДАННЫХ И МИГРАЦИИ ----------------
db = sqlite3.connect("fitness.db")
cur = db.cursor()

try:
    cur.execute(
        "CREATE TABLE IF NOT EXISTS programs(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, order_index INTEGER DEFAULT 0)")
    cur.execute(
        "CREATE TABLE IF NOT EXISTS exercises(id INTEGER PRIMARY KEY AUTOINCREMENT, program_id INTEGER, name TEXT, sets INTEGER, reps INTEGER, weight REAL, order_index INTEGER DEFAULT 0)")
    cur.execute(
        "CREATE TABLE IF NOT EXISTS calendar(id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, program_id INTEGER, status TEXT)")
    cur.execute(
        "CREATE TABLE IF NOT EXISTS pet_settings(id INTEGER PRIMARY KEY, p_type TEXT, bottom_only INTEGER, immortal INTEGER, disabled INTEGER, size REAL, happiness INTEGER, total_xp REAL)")

    try:
        cur.execute("ALTER TABLE programs ADD COLUMN order_index INTEGER DEFAULT 0")
    except:
        pass
    try:
        cur.execute("ALTER TABLE exercises ADD COLUMN order_index INTEGER DEFAULT 0")
    except:
        pass

    cur.execute("SELECT id, p_type FROM pet_settings WHERE id=1")
    row = cur.fetchone()
    if not row:
        cur.execute(
            "INSERT INTO pet_settings(id, p_type, bottom_only, immortal, disabled, size, happiness, total_xp) VALUES(1, 'spongebob.png', 1, 0, 0, 80, 100, 0)")
    else:
        if row[1] not in ['spongebob.png', 'patrick.png', 'gary.png']:
            cur.execute("UPDATE pet_settings SET p_type='spongebob.png' WHERE id=1")
    db.commit()
except Exception as e:
    print(f"DB INIT ERROR: {e}")


def format_weight(weight):
    try:
        w = float(weight)
        return str(int(w)) if w.is_integer() else str(w)
    except:
        return "0"


def get_contrast_color(rgba):
    r, g, b = rgba[:3]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    return (0.1, 0.1, 0.1, 1) if y > 0.5 else (1, 1, 1, 1)


# ---------------- 2. БАЗОВЫЕ КОМПОНЕНТЫ DESIGN SYSTEM ----------------

class AppBaseModalView(ModalView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_color = (0, 0, 0, 0.7)
        self.app = App.get_running_app()

        with self.canvas.before:
            self._bg_color = Color(rgba=self.app.card_color)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[self.app.radius_card])

        self.bind(pos=self._update_canvas_bounds, size=self._update_canvas_bounds)
        self.app.bind(card_color=self._update_theme_color)

    def _update_canvas_bounds(self, *args):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def _update_theme_color(self, instance, value):
        self._bg_color.rgba = value


class AppBaseBottomSheet(ModalView):
    def __init__(self, height_ratio=0.75, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (1, height_ratio)
        self.pos_hint = {'bottom': 1}
        self.background_color = (0, 0, 0, 0.7)
        self.auto_dismiss = True
        self.app = App.get_running_app()

        with self.canvas.before:
            self._bg_color = Color(rgba=self.app.menu_bg_color)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(24), dp(24), 0, 0])

        self.bind(pos=self._update_canvas_bounds, size=self._update_canvas_bounds)
        self.app.bind(menu_bg_color=self._update_theme_color)

    def _update_canvas_bounds(self, *args):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def _update_theme_color(self, instance, value):
        self._bg_color.rgba = value


class DragHandle(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.size = (dp(50), dp(5))
        self.pos_hint = {'center_x': 0.5}
        with self.canvas.before:
            Color(0.5, 0.5, 0.5, 0.5)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(2.5)])
        self.bind(pos=self.update_rect, size=self.update_rect)

    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size


# ---------------- 3. ИИ-ПИТОМЕЦ: ЛОГИКА ДВИЖЕНИЯ И ФРАЗ ----------------

class LivePetWidget(ButtonBehavior, FloatLayout):
    angle = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, None)

        with self.canvas.before:
            PushMatrix()
            self.rot = Rotate(angle=self.angle, origin=self.center)
        with self.canvas.after:
            PopMatrix()

        self.bind(pos=self.update_rot, size=self.update_rot)

        self.pet_img = Image(allow_stretch=True, keep_ratio=True, size_hint=(1, 1),
                             pos_hint={'center_x': 0.5, 'center_y': 0.5})
        self.chat_label = Label(markup=True, halign='center', valign='bottom', size_hint=(1.5, 0.5),
                                pos_hint={'center_x': 0.5, 'y': 0.95})
        self.chat_label.bind(size=lambda inst, val: setattr(inst, 'text_size', val))

        self.add_widget(self.pet_img)
        self.add_widget(self.chat_label)

        # Системные переменные ИИ
        self.is_sleeping = False
        self.is_interacting = False  # Блокиратор спама кликов

        # Пулы фраз
        self.phrases_click = ["Эй, щекотно!", "Чего изволите?", "Опа!", "Дай пять ✋", "К тренировке готов!"]
        self.phrases_happy = ["Отличный день!", "Мышцы горят!", "Время бить рекорды!", "Суперсет? Легко!"]
        self.phrases_normal = ["Просто гуляю...", "Разминаюсь...", "Что сегодня качаем?", "Ищу протеин..."]
        self.phrases_sad = ["Мне скучно...", "Забыли про меня? 😿", "Энергия на нуле...", "Пора бы позаниматься..."]

        self.load_settings()

        Clock.schedule_once(self.decide_next_action, 2.0)
        self.drain_event = Clock.schedule_interval(self.drain_happiness, 3600.0)

    def on_angle(self, instance, value):
        if hasattr(self, 'rot'): self.rot.angle = value

    def update_rot(self, *args):
        if hasattr(self, 'rot'): self.rot.origin = self.center

    def load_settings(self):
        cur.execute(
            "SELECT p_type, bottom_only, immortal, disabled, size, happiness, total_xp FROM pet_settings WHERE id=1")
        data = cur.fetchone()
        if data:
            self.p_type, self.bottom_only, self.immortal, self.disabled_pet, sz, self.happiness, self.total_xp = data
            self.size = (dp(sz), dp(sz))
            self.chat_label.font_size = f"{sz * 0.2}sp"
            self.update_visual()

    def save_settings(self):
        cur.execute(
            "UPDATE pet_settings SET p_type=?, bottom_only=?, immortal=?, disabled=?, size=?, happiness=?, total_xp=? WHERE id=1",
            (self.p_type, self.bottom_only, self.immortal, self.disabled_pet, self.size[0] / dp(1), self.happiness,
             self.total_xp))
        db.commit()

    def update_visual(self):
        if self.disabled_pet:
            self.opacity = 0
            return
        self.opacity = 1
        self.pet_img.source = self.p_type

        hour = datetime.datetime.now().hour
        self.is_sleeping = (23 <= hour or hour < 7)

        if self.is_sleeping:
            self.chat_label.text = "[color=#A0A0FF]💤[/color]"
        elif not self.is_interacting:
            lvl = 1 + int(self.total_xp // 1000)
            mood = "💪" if lvl >= 10 else "😎" if lvl >= 5 else ""
            app = App.get_running_app()
            if mood and app:
                c_hex = '#%02x%02x%02x' % tuple(int(c * 255) for c in app.text_color[:3])
                self.chat_label.text = f"[color={c_hex}]{mood} Lvl {lvl}[/color]"
            else:
                self.chat_label.text = ""

    def decide_next_action(self, *args):
        if self.disabled_pet or self.is_sleeping or self.is_interacting:
            Clock.schedule_once(self.decide_next_action, 2.0)
            return

        Animation.cancel_all(self)

        # Защита от выхода за экран при изменении настроек на лету
        max_x = max(0, Window.width - self.width)
        max_y = dp(150) if self.bottom_only else max(0, Window.height - self.height)
        if self.y > max_y: self.y = max_y
        if self.x > max_x: self.x = max_x

        # 70% шанс на ходьбу, 30% шанс на паузу/остановку
        is_walk = random.random() < 0.70

        # Случайные разговорные фразы во время бездействия
        if random.random() < 0.25:
            self.show_random_phrase()

        if is_walk:
            nx = random.uniform(0, max_x)
            ny = random.uniform(0, max_y)
            dur = random.uniform(2.5, 4.5)
            anim = Animation(pos=(nx, ny), duration=dur, t='in_out_sine')
            anim.bind(on_complete=lambda *x: Clock.schedule_once(self.decide_next_action, random.uniform(0.5, 1.5)))
            anim.start(self)
        else:
            # Пауза/отдых
            dur = random.uniform(1.5, 3.0)
            special = random.random()

            if special < 0.15:  # Редкий прыжок
                jy = min(self.y + dp(30), max_y)
                if jy <= self.y: jy = self.y + dp(10)
                anim = Animation(y=jy, duration=0.3, t='out_quad') + Animation(y=self.y, duration=0.3, t='out_bounce')
            elif special < 0.30:  # Редкое вращение
                anim = Animation(angle=360, duration=0.8, t='in_out_quad')
                anim.bind(on_complete=lambda *args: setattr(self, 'angle', 0))
            else:  # Обычная остановка (эффект дыхания)
                oy = self.y
                anim = Animation(y=oy + dp(4), duration=dur / 2, t='in_out_quad') + Animation(y=oy, duration=dur / 2,
                                                                                              t='in_out_quad')

            anim.bind(on_complete=lambda *x: Clock.schedule_once(self.decide_next_action, 0.5))
            anim.start(self)

    def show_random_phrase(self):
        if self.happiness > 70:
            pool = self.phrases_happy
        elif self.happiness > 30:
            pool = self.phrases_normal
        else:
            pool = self.phrases_sad

        phrase = random.choice(pool)
        self._set_chat_text(phrase)
        Clock.unschedule(self._clear_chat)
        Clock.schedule_once(self._clear_chat, 3.0)

    def _set_chat_text(self, text):
        app = App.get_running_app()
        c_hex = '#%02x%02x%02x' % tuple(int(c * 255) for c in app.text_color[:3]) if app else "#FFFFFF"
        self.chat_label.text = f"[b][color={c_hex}]{text}[/color][/b]"

    def _clear_chat(self, dt):
        if not self.is_interacting:
            self.update_visual()

    def drain_happiness(self, dt):
        if not self.immortal and not self.disabled_pet:
            self.happiness = max(0, self.happiness - 5)
            self.save_settings()

    def on_touch_down(self, touch):
        # ЗАЩИТА: Блокировка спам-кликов через is_interacting
        if self.collide_point(*touch.pos) and not self.disabled_pet and not self.is_interacting:
            hour = datetime.datetime.now().hour
            if not (23 <= hour or hour < 7):
                self.is_interacting = True
                Animation.cancel_all(self)  # Останавливаем любой бег

                self.happiness = min(100, self.happiness + 15)
                self.save_settings()

                # Рандомная реакция
                self._set_chat_text(random.choice(self.phrases_click))

                max_y = dp(150) if self.bottom_only else max(0, Window.height - self.height)
                action = random.choice(['jump', 'shake', 'spin'])

                if action == 'jump':
                    jy = min(self.y + dp(30), max_y)
                    if jy <= self.y: jy = self.y + dp(10)
                    anim = Animation(y=jy, duration=0.15, t='out_quad') + Animation(y=self.y, duration=0.2,
                                                                                    t='out_bounce')
                elif action == 'shake':
                    ox = self.x
                    anim = Animation(x=ox - dp(10), duration=0.05) + Animation(x=ox + dp(10), duration=0.1) + Animation(
                        x=ox, duration=0.05)
                elif action == 'spin':
                    anim = Animation(angle=360, duration=0.5, t='in_out_quad')
                    anim.bind(on_complete=lambda *args: setattr(self, 'angle', 0))

                def end_interact(*args):
                    self.is_interacting = False
                    self.update_visual()
                    Clock.schedule_once(self.decide_next_action, 0.5)

                anim.bind(on_complete=end_interact)
                anim.start(self)
            return True
        return super().on_touch_down(touch)

    def add_xp(self, volume):
        self.total_xp += volume
        self.save_settings()
        self.update_visual()


# ---------------- 3.1 ОСТАЛЬНЫЕ КОМПОНЕНТЫ УПРАВЛЕНИЯ ----------------

class LockableCarousel(Carousel):
    swipe_locked = False

    def on_touch_down(self, touch):
        if self.swipe_locked and self.collide_point(*touch.pos):
            for child in self.children:
                if child.dispatch('on_touch_down', touch): return True
            return False
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if self.swipe_locked: return False
        return super().on_touch_move(touch)


class SmoothColorWheel(ButtonBehavior, BoxLayout):
    __events__ = ('on_color_change',)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self.draw_wheel, size=self.draw_wheel)
        self.current_hsv = (0, 1, 1)

    def draw_wheel(self, *args):
        self.canvas.clear()
        cx, cy = self.center_x, self.center_y
        radius = min(self.width, self.height) / 2 * 0.95
        segments = 60
        with self.canvas:
            for i in range(segments):
                a1 = math.radians(i * (360 / segments))
                a2 = math.radians((i + 1) * (360 / segments))
                x1, y1 = cx + radius * math.cos(a1), cy + radius * math.sin(a1)
                x2, y2 = cx + radius * math.cos(a2), cy + radius * math.sin(a2)
                r, g, b = colorsys.hsv_to_rgb(i / segments, 1, 1)
                Color(r, g, b)
                Triangle(points=[cx, cy, x1, y1, x2, y2])
            Color(1, 1, 1, 0.2)
            Ellipse(pos=(cx - radius * 0.3, cy - radius * 0.3), size=(radius * 0.6, radius * 0.6))

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self.update_color(touch)
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if self.collide_point(*touch.pos):
            self.update_color(touch)
            return True
        return super().on_touch_move(touch)

    def update_color(self, touch):
        cx, cy = self.center_x, self.center_y
        radius = min(self.width, self.height) / 2 * 0.95
        dx, dy = touch.x - cx, touch.y - cy
        angle = math.atan2(dy, dx)
        if angle < 0: angle += 2 * math.pi
        self.current_hsv = (angle / (2 * math.pi), min(1.0, math.hypot(dx, dy) / radius), 1.0)
        self.dispatch('on_color_change')

    def on_color_change(self, *args):
        pass


class StyledButton(Button):
    bg_color_prop = ListProperty([0.5, 0.5, 0.5, 1])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ""
        self.background_color = (0, 0, 0, 0)
        self.font_name = "Roboto"
        self.bold = True
        self.markup = True
        app = App.get_running_app()
        self.bind(bg_color_prop=self.update_contrast)
        with self.canvas.before:
            self.bg_color = Color(rgba=self.bg_color_prop)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[app.radius_button])
        self.bind(pos=self.update_rect, size=self.update_rect)

    def on_bg_color_prop(self, instance, value):
        self.bg_color.rgba = value
        self.update_contrast()

    def update_contrast(self, *args):
        self.color = get_contrast_color(self.bg_color.rgba)

    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size


class CircularFAB(Button):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.text = "+"
        self.font_size = '32sp'
        self.bold = True
        self.size_hint = (None, None)
        self.size = (dp(60), dp(60))
        self.background_normal = ""
        self.background_color = (0, 0, 0, 0)
        app = App.get_running_app()
        with self.canvas.before:
            self.circle_color = Color(rgba=app.primary_btn_color)
            self.circle_shape = Ellipse(pos=self.pos, size=self.size)
        app.bind(primary_btn_color=self.on_primary_color_change)
        self.bind(pos=self.update_canvas, size=self.update_canvas)
        self.on_primary_color_change(None, app.primary_btn_color)

    def on_primary_color_change(self, instance, value):
        self.circle_color.rgba = value
        self.color = get_contrast_color(value)

    def update_canvas(self, *args):
        self.circle_shape.pos = self.pos
        self.circle_shape.size = self.size


class StatBadge(BoxLayout):
    def __init__(self, title, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = dp(10)
        app = App.get_running_app()

        with self.canvas.before:
            self.bg_color = Color(rgba=app.menu_bg_color)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(12)])

        self.bind(pos=self.update_rect, size=self.update_rect)

        self.val_lbl = Label(text="-", font_name="Roboto", font_size='24sp', bold=True, color=app.text_color,
                             size_hint_y=0.6)
        self.title_lbl = Label(text=title, font_name="Roboto", font_size='11sp', bold=True, color=app.sub_text_color,
                               size_hint_y=0.4)

        self.add_widget(self.val_lbl)
        self.add_widget(self.title_lbl)

    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size

    def set_val(self, val):
        self.val_lbl.text = str(val)


class RoundedCRUDCard(DragBehavior, BoxLayout):
    def __init__(self, item_id, title_text, sub_text, edit_callback, delete_callback, click_callback, reorder_callback,
                 **kwargs):
        super().__init__(**kwargs)
        self.item_id = item_id
        self.reorder_callback = reorder_callback
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = dp(85)
        app = App.get_running_app()
        self.padding = app.pad_standard[0]
        self.spacing = app.spacing_standard

        with self.canvas.before:
            self.bg_color = Color(rgba=app.card_color)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[app.radius_card])
        self.bind(pos=self.update_rect, size=self.update_rect)

        left_container = FloatLayout(size_hint_x=1)
        text_box = BoxLayout(orientation='vertical', spacing=dp(4), size_hint=(1, 1), pos_hint={'x': 0, 'y': 0})
        self.title_lbl = Label(text=title_text, font_name="Roboto", font_size="18sp", bold=True,
                               halign="left", valign="middle", color=app.text_color, shorten=True, shorten_from="right")
        self.title_lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', val))
        self.sub_lbl = Label(text=sub_text, font_name="Roboto", font_size="14sp", color=app.sub_text_color,
                             halign="left", valign="middle", shorten=True, shorten_from="right")
        self.sub_lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', val))

        text_box.add_widget(self.title_lbl)
        text_box.add_widget(self.sub_lbl)

        click_overlay = Button(background_normal="", background_color=(0, 0, 0, 0), size_hint=(1, 1),
                               pos_hint={'x': 0, 'y': 0})
        click_overlay.bind(on_press=click_callback)
        left_container.add_widget(text_box)
        left_container.add_widget(click_overlay)
        self.add_widget(left_container)

        self.crud_box = BoxLayout(orientation='horizontal', size_hint_x=None, width=dp(0), spacing=dp(5), opacity=0)
        self.edit_btn = Button(text="✎", font_name="Roboto", font_size="22sp", background_normal="",
                               background_color=(0, 0, 0, 0), color=app.text_color)
        self.delete_btn = Button(text="🗑", font_name="Roboto", font_size="22sp", background_normal="",
                                 background_color=(0, 0, 0, 0), color=(1, 0.3, 0.3, 1))
        self.drag_handle = Label(text="≡", font_name="Roboto", font_size="28sp", color=app.sub_text_color,
                                 size_hint_x=None, width=dp(40))

        self.edit_btn.bind(on_press=edit_callback)
        self.delete_btn.bind(on_press=delete_callback)
        self.crud_box.add_widget(self.edit_btn)
        self.crud_box.add_widget(self.delete_btn)
        self.crud_box.add_widget(self.drag_handle)

        self.add_widget(self.crud_box)

    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size

    def toggle_edit(self, is_edit):
        self.crud_box.opacity = 1 if is_edit else 0
        self.crud_box.disabled = not is_edit
        self.crud_box.width = dp(120) if is_edit else dp(0)

    def on_touch_down(self, touch):
        if self.crud_box.opacity == 1 and self.drag_handle.collide_point(*touch.pos):
            self._custom_drag_touch = touch
            touch.grab(self)

            self.parent_layout = self.parent
            abs_x, abs_y = self.to_window(self.x, self.y)
            exact_width = self.width
            exact_height = self.height

            self.placeholder = BoxLayout(size_hint_y=None, height=exact_height)

            idx = self.parent_layout.children.index(self)
            self.parent_layout.remove_widget(self)
            self.parent_layout.add_widget(self.placeholder, index=idx)

            Window.add_widget(self)
            self.size_hint = (None, None)
            self.size = (exact_width, exact_height)
            self.pos = (abs_x, abs_y)
            self.opacity = 0.85
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.grab_current is self and getattr(self, '_custom_drag_touch', None) == touch:
            self.center_y = touch.y

            for i, child in enumerate(self.parent_layout.children):
                if child is not self.placeholder:
                    _, child_cy = child.to_window(child.center_x, child.center_y)
                    if abs(touch.y - child_cy) < (child.height * 0.5):
                        p_idx = self.parent_layout.children.index(self.placeholder)
                        if i != p_idx:
                            self.parent_layout.children[p_idx], self.parent_layout.children[i] = \
                                self.parent_layout.children[i], self.parent_layout.children[p_idx]
                            self.parent_layout.do_layout()
                        break
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self and getattr(self, '_custom_drag_touch', None) == touch:
            touch.ungrab(self)
            self._custom_drag_touch = None

            Window.remove_widget(self)

            idx = self.parent_layout.children.index(self.placeholder)
            self.parent_layout.remove_widget(self.placeholder)

            self.size_hint = (1, None)
            self.opacity = 1
            self.parent_layout.add_widget(self, index=idx)

            if self.reorder_callback:
                self.reorder_callback()
            return True
        return super().on_touch_up(touch)


class DayButton(ButtonBehavior, BoxLayout):
    def __init__(self, text_day, date_str, status, is_today, prog_name="", **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = dp(4)
        self.date_str = date_str
        self.status = status
        app = App.get_running_app()

        with self.canvas.before:
            bg = app.primary_btn_color if status == 'completed' else app.card_color
            self.bg_color = Color(rgba=bg)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[app.radius_small])
            if status == 'planned':
                self.line_color = Color(rgba=app.primary_btn_color)
                self.line = Line(width=1.5,
                                 rounded_rectangle=(self.x, self.y, self.width, self.height, app.radius_small))
        self.bind(pos=self.update_rect, size=self.update_rect)

        t_color = get_contrast_color(bg) if status == 'completed' else (
            (1, 0.4, 0.4, 1) if is_today else app.text_color)
        self.lbl_day = Label(text=str(text_day), font_name="Roboto", bold=is_today, color=t_color, size_hint_y=0.6,
                             font_size='14sp')

        sub_color = get_contrast_color(bg) if status == 'completed' else app.sub_text_color
        self.lbl_prog = Label(text=prog_name, font_name="Roboto", color=sub_color, size_hint_y=0.4, font_size='10sp',
                              shorten=True, shorten_from="right", halign="center", valign="middle")
        self.lbl_prog.bind(size=lambda inst, val: setattr(inst, 'text_size', val))

        self.add_widget(self.lbl_day)
        self.add_widget(self.lbl_prog)

    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size
        if hasattr(self, 'line'):
            self.line.rounded_rectangle = (self.x, self.y, self.width, self.height, App.get_running_app().radius_small)


# ---------------- 4. ГЛАВНЫЙ ЭКРАН ----------------

class HomeScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.edit_mode = False
        self.menu_open = False
        self.build_ui()
        Clock.schedule_once(self.set_default_slide, 0)

    def set_default_slide(self, dt):
        self.carousel.load_slide(self.carousel.slides[1])

    def on_pre_enter(self):
        self.apply_theme_styles()
        self.load_programs()
        self.populate_calendar()

    def apply_theme_styles(self):
        app = App.get_running_app()
        self.bg_color_ctx.rgba = app.bg_color
        self.top_bar_color.rgba = app.card_color
        self.title_lbl.color = app.text_color
        self.menu_btn.color = app.text_color
        self.edit_toggle_btn.color = app.primary_btn_color if self.edit_mode else app.text_color
        self.multi_btn.color = app.text_color
        self.menu_color.rgba = app.menu_bg_color
        self.wotd_color.rgba = app.card_color
        self.streak_label.color = app.primary_btn_color if app.accent_mode != "mono" else app.text_color
        self.month_label.color = app.text_color

    def toggle_edit_mode(self, instance):
        self.edit_mode = not self.edit_mode
        app = App.get_running_app()
        self.carousel.swipe_locked = self.edit_mode
        instance.color = app.primary_btn_color if self.edit_mode else app.text_color
        self.load_programs()

    def update_dots(self, instance, value):
        app = App.get_running_app()
        for i, dot in enumerate(self.dots):
            dot.text = "●" if i == value else "○"
            dot.color = app.text_color if i == value else (0.5, 0.5, 0.5, 1)

        if hasattr(self, 'fab_btn'):
            self.fab_btn.opacity = 1 if value == 1 else 0
            self.fab_btn.disabled = value != 1

    def toggle_menu(self, instance):
        if not self.menu_open:
            self.overlay.size_hint = (1, 1)
            Animation(pos=(0, 0), duration=0.2, t="out_quad").start(self.menu)
            Animation(background_color=(0, 0, 0, 0.5), duration=0.2).start(self.overlay)
        else:
            Animation(pos=(-260, 0), duration=0.2, t="out_quad").start(self.menu)
            anim = Animation(background_color=(0, 0, 0, 0), duration=0.2)
            anim.bind(on_complete=lambda *args: setattr(self.overlay, 'size_hint', (0, 0)))
            anim.start(self.overlay)
        self.menu_open = not self.menu_open

    def open_theme_popup_routing(self, instance):
        self.toggle_menu(None)
        App.get_running_app().open_theme_popup()

    def open_pet_popup_routing(self, instance):
        self.toggle_menu(None)
        App.get_running_app().open_pet_settings()

    def open_multi_select(self, instance):
        cur.execute("SELECT id, name FROM programs ORDER BY order_index ASC")
        progs = cur.fetchall()
        if not progs: return

        app = App.get_running_app()
        sheet = AppBaseBottomSheet(height_ratio=0.75)

        layout = BoxLayout(orientation='vertical', padding=dp(15), spacing=dp(10))
        layout.add_widget(DragHandle())

        header_box = BoxLayout(orientation='horizontal', size_hint_y=0.1)
        title_lbl = Label(text="МУЛЬТИ-ТРЕНИРОВКА", font_name="Roboto", bold=True, color=app.text_color, halign="left",
                          valign="middle")
        title_lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', val))

        close_btn = Button(text="✕", font_name="Roboto", font_size="24sp", background_normal="",
                           background_color=(0, 0, 0, 0), color=app.text_color, size_hint_x=None, width=dp(40))
        close_btn.bind(on_press=sheet.dismiss)

        header_box.add_widget(title_lbl)
        header_box.add_widget(close_btn)
        layout.add_widget(header_box)

        selected_ids = []
        scroll = ScrollView()
        box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)
        box.bind(minimum_height=box.setter('height'))

        start_btn = StyledButton(text="НАЧАТЬ (0)", size_hint_y=None, height=dp(50))
        start_btn.bg_color_prop = app.card_color

        def update_start_btn():
            start_btn.text = f"НАЧАТЬ ({len(selected_ids)})"
            if len(selected_ids) > 0:
                start_btn.bg_color_prop = app.primary_btn_color
            else:
                start_btn.bg_color_prop = app.card_color

        for p in progs:
            b = StyledButton(text=p[1], size_hint_y=None, height=dp(48))
            b.bg_color_prop = app.card_color
            b.color = app.text_color

            def toggle_prog(inst, pid=p[0]):
                if pid in selected_ids:
                    selected_ids.remove(pid)
                    inst.bg_color_prop = app.card_color
                else:
                    selected_ids.append(pid)
                    inst.bg_color_prop = app.primary_btn_color
                update_start_btn()

            b.bind(on_press=toggle_prog)
            box.add_widget(b)

        scroll.add_widget(box)
        layout.add_widget(scroll)

        def launch_multi(inst):
            if not selected_ids: return
            sheet.dismiss()
            multi_data = []
            for pid in selected_ids:
                cur.execute("SELECT name FROM programs WHERE id=?", (pid,))
                pname = cur.fetchone()[0]
                cur.execute(
                    "SELECT id, program_id, name, sets, reps, weight FROM exercises WHERE program_id=? ORDER BY order_index ASC",
                    (pid,))
                exs = cur.fetchall()
                if exs:
                    multi_data.append({"program_id": pid, "name": pname, "queue": exs, "curr_idx": 0})

            if multi_data:
                app.animate_screen_transition(self.manager, "player", "left")
                player = self.manager.get_screen("player")
                player.load_multi_queue(multi_data)

        start_btn.bind(on_press=launch_multi)
        layout.add_widget(start_btn)
        sheet.add_widget(layout)
        sheet.open()

    def build_ui(self):
        root = FloatLayout()
        app = App.get_running_app()

        with self.canvas.before:
            self.bg_color_ctx = Color(rgba=(0, 0, 0, 1))
            self.bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda obj, val: setattr(self.bg_rect, 'pos', val),
                  size=lambda obj, val: setattr(self.bg_rect, 'size', val))

        self.fab_btn = CircularFAB(pos_hint={'right': 0.95, 'y': 0.05})
        self.fab_btn.bind(on_press=self.create_program)

        content_box = BoxLayout(orientation="vertical", size_hint=(1, 1))

        self.top_bar = BoxLayout(orientation="horizontal", size_hint=(1, 0.1), spacing=10, padding=10)
        with self.top_bar.canvas.before:
            self.top_bar_color = Color(rgba=(0.1, 0.1, 0.1, 1))
            self.top_bar_rect = Rectangle(pos=self.top_bar.pos, size=self.top_bar.size)
        self.top_bar.bind(pos=lambda obj, val: setattr(self.top_bar_rect, 'pos', val),
                          size=lambda obj, val: setattr(self.top_bar_rect, 'size', val))

        self.menu_btn = Button(text="☰", font_name="Roboto", font_size="22sp", background_normal="",
                               background_color=(0, 0, 0, 0), size_hint=(0.15, 1))
        self.menu_btn.bind(on_press=self.toggle_menu)

        self.title_lbl = Label(text="МОИ ТРЕНИРОВКИ", font_name="Roboto", bold=True, size_hint=(0.55, 1))

        self.multi_btn = Button(text="🔀", font_name="Roboto", font_size="20sp", background_normal="",
                                background_color=(0, 0, 0, 0), size_hint=(0.15, 1))
        self.multi_btn.bind(on_press=self.open_multi_select)

        self.edit_toggle_btn = Button(text="✏", font_name="Roboto", font_size="20sp", background_normal="",
                                      background_color=(0, 0, 0, 0), size_hint=(0.15, 1))
        self.edit_toggle_btn.bind(on_press=self.toggle_edit_mode)

        self.top_bar.add_widget(self.menu_btn)
        self.top_bar.add_widget(self.title_lbl)
        self.top_bar.add_widget(self.multi_btn)
        self.top_bar.add_widget(self.edit_toggle_btn)
        content_box.add_widget(self.top_bar)

        dots_layout = BoxLayout(orientation='horizontal', size_hint=(1, None), height=20, spacing=10)
        dots_layout.add_widget(Label(size_hint_x=1))
        self.dots = []
        for i in range(3):
            dot = Label(text="○", font_size='16sp', size_hint_x=None, width=20, color=(0.5, 0.5, 0.5, 1))
            self.dots.append(dot)
            dots_layout.add_widget(dot)
        dots_layout.add_widget(Label(size_hint_x=1))
        content_box.add_widget(dots_layout)

        self.carousel = LockableCarousel(direction='right', size_hint=(1, 0.88))
        self.carousel.bind(index=self.update_dots)

        chat_slide = BoxLayout(orientation='vertical', padding=15)
        chat_slide.add_widget(
            Label(text="🤖\nИИ-Чат\n(в разработке)", font_name="Roboto", font_size='22sp', halign="center"))

        main_slide = BoxLayout(orientation="vertical", padding=[16, 0, 16, 16], spacing=15)
        scroll = ScrollView()
        self.programs_box = BoxLayout(orientation="vertical", spacing=12, size_hint_y=None, padding=[0, 0, 0, dp(80)])
        self.programs_box.bind(minimum_height=self.programs_box.setter("height"))
        scroll.add_widget(self.programs_box)
        main_slide.add_widget(scroll)

        self.calendar_slide = BoxLayout(orientation='vertical', padding=14, spacing=10)
        cal_top = BoxLayout(orientation='horizontal', size_hint=(1, 0.12), spacing=10)
        self.streak_label = Label(text="🔥 0", font_name="Roboto", font_size='22sp', size_hint=(0.25, 1), bold=True)
        repeat_btn = StyledButton(text="Повторить прошлую неделю", size_hint=(0.75, 1))
        repeat_btn.bind(on_press=self.repeat_last_week)
        cal_top.add_widget(self.streak_label)
        cal_top.add_widget(repeat_btn)
        self.calendar_slide.add_widget(cal_top)

        self.month_label = Label(text="", font_name="Roboto", size_hint=(1, 0.05), bold=True, font_size='18sp')
        self.calendar_slide.add_widget(self.month_label)

        self.cal_grid = GridLayout(cols=7, size_hint=(1, 0.53), spacing=6)
        self.calendar_slide.add_widget(self.cal_grid)

        self.wotd_box = BoxLayout(orientation='vertical', size_hint=(1, 0.3), padding=15, spacing=5)
        with self.wotd_box.canvas.before:
            self.wotd_color = Color(rgba=(0, 0, 0, 1))
            self.wotd_bg = RoundedRectangle(pos=self.wotd_box.pos, size=self.wotd_box.size, radius=[app.radius_card])
        self.wotd_box.bind(pos=lambda obj, val: setattr(self.wotd_bg, 'pos', val),
                           size=lambda obj, val: setattr(self.wotd_bg, 'size', val))

        self.wotd_content = BoxLayout(orientation='vertical', size_hint=(1, 1))
        self.wotd_box.add_widget(self.wotd_content)
        self.calendar_slide.add_widget(self.wotd_box)

        self.carousel.add_widget(chat_slide)
        self.carousel.add_widget(main_slide)
        self.carousel.add_widget(self.calendar_slide)
        content_box.add_widget(self.carousel)
        root.add_widget(content_box)

        self.overlay = Button(background_normal="", background_color=(0, 0, 0, 0), size_hint=(0, 0),
                              pos_hint={"x": 0, "y": 0})
        self.overlay.bind(on_press=self.toggle_menu)
        root.add_widget(self.overlay)

        self.menu = BoxLayout(orientation="vertical", size_hint=(None, 1), width=260, pos=(-260, 0), spacing=10,
                              padding=15)
        with self.menu.canvas.before:
            self.menu_color = Color(rgba=(0.1, 0.1, 0.1, 1))
            self.menu_bg = Rectangle(size=self.menu.size, pos=self.menu.pos)
            self.menu.bind(pos=lambda obj, val: setattr(self.menu_bg, 'pos', val),
                           size=lambda obj, val: setattr(self.menu_bg, 'size', val))

        an_btn = Button(text="-> Аналитика", font_name="Roboto", size_hint_y=0.1, background_normal="",
                        background_color=(0, 0, 0, 0), color=(1, 1, 1, 1))
        self.menu.add_widget(an_btn)

        pet_routing_btn = Button(text="🐾 Питомец", font_name="Roboto", size_hint_y=0.1, background_normal="",
                                 background_color=(0, 0, 0, 0), color=(1, 1, 1, 1))
        pet_routing_btn.bind(on_press=self.open_pet_popup_routing)
        self.menu.add_widget(pet_routing_btn)

        self.theme_routing_btn = Button(text="🎨 Темы", font_name="Roboto", size_hint_y=0.1, background_normal="",
                                        background_color=(0, 0, 0, 0), color=(1, 1, 1, 1))
        self.theme_routing_btn.bind(on_press=self.open_theme_popup_routing)
        self.menu.add_widget(self.theme_routing_btn)
        self.menu.add_widget(Label(size_hint_y=0.6))

        close_menu_btn = StyledButton(text="Закрыть", size_hint_y=0.1)
        close_menu_btn.bg_color_prop = (0.3, 0.3, 0.3, 1)
        close_menu_btn.bind(on_press=self.toggle_menu)
        self.menu.add_widget(close_menu_btn)
        root.add_widget(self.menu)

        root.add_widget(self.fab_btn)
        self.add_widget(root)

    def load_programs(self):
        try:
            self.programs_box.clear_widgets()
            cur.execute("SELECT * FROM programs ORDER BY order_index ASC")
            for row in cur.fetchall():
                cur.execute("SELECT COUNT(*) FROM exercises WHERE program_id=?", (row[0],))
                count = cur.fetchone()[0]
                card = RoundedCRUDCard(
                    item_id=row[0],
                    title_text=row[1],
                    sub_text=f"Упражнений: {count}",
                    edit_callback=lambda x, pid=row[0]: self.edit_program(pid),
                    delete_callback=lambda x, pid=row[0]: self.delete_program(pid),
                    click_callback=lambda x, pid=row[0]: self.open_program(pid),
                    reorder_callback=self.save_program_order
                )
                card.toggle_edit(self.edit_mode)
                self.programs_box.add_widget(card)
        except Exception as e:
            print("DB Load Programs Error:", e)

    def save_program_order(self):
        try:
            for i, card in enumerate(reversed(self.programs_box.children)):
                cur.execute("UPDATE programs SET order_index=? WHERE id=?", (i, card.item_id))
            db.commit()
        except Exception as e:
            print("Order save error:", e)

    def create_program(self, instance):
        app = App.get_running_app()
        layout = BoxLayout(orientation="vertical", spacing=app.spacing_compact, padding=app.pad_standard[0])
        name_input = TextInput(hint_text="Название программы", font_name="Roboto", multiline=False, size_hint_y=None,
                               height=app.height_input)
        save_btn = StyledButton(text="Создать", size_hint_y=None, height=app.height_button)
        save_btn.bg_color_prop = app.primary_btn_color
        layout.add_widget(name_input)
        layout.add_widget(save_btn)

        popup = AppBaseModalView(size_hint=(0.85, 0.3))

        def save(inst):
            try:
                cur.execute("SELECT MAX(order_index) FROM programs")
                max_order = cur.fetchone()[0]
                nxt = 0 if max_order is None else max_order + 1
                cur.execute("INSERT INTO programs(name, order_index) VALUES(?, ?)",
                            (name_input.text.strip() or "Без названия", nxt))
                db.commit()
                popup.dismiss()
                self.load_programs()
            except Exception as e:
                print("DB Save Error:", e)

        save_btn.bind(on_press=save)
        popup.add_widget(layout)
        popup.open()

    def edit_program(self, program_id):
        app = App.get_running_app()
        cur.execute("SELECT name FROM programs WHERE id=?", (program_id,))
        current_name = cur.fetchone()[0]

        layout = BoxLayout(orientation="vertical", spacing=app.spacing_compact, padding=app.pad_standard[0])
        name_input = TextInput(text=current_name, font_name="Roboto", multiline=False, size_hint_y=None,
                               height=app.height_input)
        save_btn = StyledButton(text="Изменить", size_hint_y=None, height=app.height_button)
        save_btn.bg_color_prop = app.primary_btn_color

        layout.add_widget(name_input)
        layout.add_widget(save_btn)

        popup = AppBaseModalView(size_hint=(0.85, 0.3))

        def save(inst):
            cur.execute("UPDATE programs SET name=? WHERE id=?", (name_input.text.strip() or "Без имени", program_id))
            db.commit()
            popup.dismiss()
            self.load_programs()

        save_btn.bind(on_press=save)
        popup.add_widget(layout)
        popup.open()

    def delete_program(self, program_id):
        cur.execute("DELETE FROM programs WHERE id=?", (program_id,))
        cur.execute("DELETE FROM exercises WHERE program_id=?", (program_id,))
        db.commit()
        self.load_programs()

    def open_program(self, program_id):
        app = App.get_running_app()
        ex_screen = self.manager.get_screen("exercises")
        ex_screen.program_id = program_id
        app.animate_screen_transition(self.manager, "exercises", "left")

    def populate_calendar(self):
        try:
            self.cal_grid.clear_widgets()
            today = datetime.date.today()
            year, month = today.year, today.month
            months_ru = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь",
                         "Ноябрь", "Декабрь"]
            self.month_label.text = f"{months_ru[month - 1]} {year}"

            cur.execute("SELECT id, name FROM programs")
            progs = {r[0]: r[1] for r in cur.fetchall()}

            for day in ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']:
                self.cal_grid.add_widget(
                    Label(text=day, font_name="Roboto", color=App.get_running_app().sub_text_color, bold=True))

            cal = pycalendar.Calendar()
            for day in cal.itermonthdates(year, month):
                date_str = day.strftime("%Y-%m-%d")
                is_today = (day == today)

                cur.execute("SELECT status, program_id FROM calendar WHERE date=?", (date_str,))
                cal_row = cur.fetchone()
                status = cal_row[0] if cal_row else 'none'
                pid = cal_row[1] if cal_row else None
                p_name = progs.get(pid, "") if pid else ""

                btn = DayButton(text_day=str(day.day), date_str=date_str, status=status, is_today=is_today,
                                prog_name=p_name)
                if day.month != month: btn.opacity = 0.3
                btn.bind(on_press=self.on_day_click)
                self.cal_grid.add_widget(btn)

            self.update_streak()
            self.update_wotd(today.strftime("%Y-%m-%d"))
        except Exception as e:
            print("Populate Calendar Error:", e)

    def on_day_click(self, instance):
        app = App.get_running_app()
        sheet = AppBaseBottomSheet(height_ratio=0.75)
        layout = BoxLayout(orientation='vertical', padding=dp(15), spacing=dp(10))

        handle = DragHandle()
        layout.add_widget(handle)

        layout.add_widget(Label(text=f"День: {instance.date_str}", font_name="Roboto", bold=True, size_hint_y=0.1,
                                color=app.text_color))

        cur.execute("SELECT id, name FROM programs ORDER BY order_index ASC")
        progs = cur.fetchall()

        scroll = ScrollView()
        box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)
        box.bind(minimum_height=box.setter('height'))

        for p in progs:
            b = StyledButton(text=p[1], size_hint_y=None, height=dp(48))
            b.bg_color_prop = app.card_color
            b.color = app.text_color

            def plan(inst, pid=p[0]):
                cur.execute("DELETE FROM calendar WHERE date=?", (instance.date_str,))
                cur.execute("INSERT INTO calendar(date, program_id, status) VALUES(?,?,?)",
                            (instance.date_str, pid, 'planned'))
                db.commit()
                self.populate_calendar()
                sheet.dismiss()

            b.bind(on_press=plan)
            box.add_widget(b)

        scroll.add_widget(box)
        layout.add_widget(scroll)

        if instance.status != 'none':
            clear_b = StyledButton(text="Очистить день", size_hint_y=None, height=dp(48))
            clear_b.bg_color_prop = (1, 0.3, 0.3, 1)

            def clear_day(inst):
                cur.execute("DELETE FROM calendar WHERE date=?", (instance.date_str,))
                db.commit()
                self.populate_calendar()
                sheet.dismiss()

            clear_b.bind(on_press=clear_day)
            layout.add_widget(clear_b)

        sheet.add_widget(layout)
        sheet.open()

    def update_streak(self):
        cur.execute("SELECT date FROM calendar WHERE status='completed' ORDER BY date DESC")
        rows = cur.fetchall()
        streak = 0
        check_date = datetime.date.today()
        dates = [datetime.datetime.strptime(r[0], "%Y-%m-%d").date() for r in rows]

        if check_date not in dates:
            check_date -= datetime.timedelta(days=1)

        for d in dates:
            if d == check_date:
                streak += 1
                check_date -= datetime.timedelta(days=1)
            elif d > check_date:
                continue
            else:
                break
        self.streak_label.text = f"🔥 {streak}"

    def update_wotd(self, today_str):
        self.wotd_content.clear_widgets()
        app = App.get_running_app()
        cur.execute(
            "SELECT c.program_id, p.name, c.status FROM calendar c JOIN programs p ON c.program_id = p.id WHERE c.date = ? ORDER BY c.id DESC LIMIT 1",
            (today_str,))
        row = cur.fetchone()

        if row and row[2] == 'planned':
            self.wotd_content.add_widget(
                Label(text=row[1], font_name="Roboto", font_size='20sp', bold=True, color=app.text_color))
            start_btn = StyledButton(text="▶ НАЧАТЬ СЕЙЧАС", bold=True, size_hint=(1, 0.6))
            start_btn.bg_color_prop = app.primary_btn_color
            start_btn.bind(on_press=lambda inst: self.start_wotd(row[0], row[1]))
            self.wotd_content.add_widget(start_btn)
        elif row and row[2] == 'completed':
            self.wotd_content.add_widget(
                Label(text="Выполнено! 💪", font_name="Roboto", color=app.primary_btn_color, font_size='18sp'))
        else:
            self.wotd_content.add_widget(
                Label(text="День отдыха ☕", font_name="Roboto", font_size='18sp', color=app.text_color))

    def start_wotd(self, program_id, p_name):
        app = App.get_running_app()
        cur.execute(
            "SELECT id, program_id, name, sets, reps, weight FROM exercises WHERE program_id=? ORDER BY order_index ASC",
            (program_id,))
        exercises = cur.fetchall()
        if not exercises:
            err = AppBaseModalView(size_hint=(0.7, 0.3))
            err.add_widget(Label(text="Сначала добавьте упражнения!", color=(1, 0.3, 0.3, 1), bold=True))
            err.open()
            return

        multi_data = [{"program_id": program_id, "name": p_name, "queue": exercises, "curr_idx": 0}]
        player = self.manager.get_screen("player")
        player.load_multi_queue(multi_data)
        app.animate_screen_transition(self.manager, "player", "left")

    def repeat_last_week(self, instance):
        try:
            today = datetime.date.today()
            start_current_week = today - datetime.timedelta(days=today.weekday())
            start_last_week = start_current_week - datetime.timedelta(days=7)

            for i in range(7):
                old_date_str = (start_last_week + datetime.timedelta(days=i)).strftime("%Y-%m-%d")
                new_date_str = (start_current_week + datetime.timedelta(days=i)).strftime("%Y-%m-%d")

                cur.execute("SELECT program_id, status FROM calendar WHERE date=?", (old_date_str,))
                row = cur.fetchone()
                if row:
                    cur.execute("DELETE FROM calendar WHERE date=?", (new_date_str,))
                    cur.execute("INSERT INTO calendar(date, program_id, status) VALUES(?,?,?)",
                                (new_date_str, row[0], 'planned'))
            db.commit()
            self.populate_calendar()
        except Exception as e:
            print("Repeat week error:", e)


# ---------------- 5. ЭКРАН СПИСКА УПРАЖНЕНИЙ ----------------

class ExercisesScreen(Screen):
    program_id = NumericProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.edit_mode = False
        self.build_ui()

    def on_pre_enter(self):
        self.apply_theme_styles()

    def apply_theme_styles(self):
        app = App.get_running_app()
        self.bg_color_ctx.rgba = app.bg_color
        self.top_bar_color.rgba = app.card_color
        self.title_label.color = app.text_color
        self.menu_btn.color = app.text_color
        self.edit_toggle_btn.color = app.primary_btn_color if self.edit_mode else app.text_color
        self.start_btn.bg_color_prop = app.primary_btn_color
        self.load_exercises()

    def toggle_edit_mode(self, instance):
        self.edit_mode = not self.edit_mode
        self.edit_toggle_btn.color = App.get_running_app().primary_btn_color if self.edit_mode else App.get_running_app().text_color
        self.load_exercises()

    def go_back_home(self, instance):
        App.get_running_app().animate_screen_transition(self.manager, "home", "right")

    def build_ui(self):
        root = FloatLayout()
        app = App.get_running_app()

        with self.canvas.before:
            self.bg_color_ctx = Color(rgba=(0, 0, 0, 1))
            self.bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda obj, val: setattr(self.bg_rect, 'pos', val),
                  size=lambda obj, val: setattr(self.bg_rect, 'size', val))

        content_box = BoxLayout(orientation="vertical", size_hint=(1, 1))

        top_bar = BoxLayout(orientation="horizontal", size_hint=(1, 0.1), spacing=10, padding=10)
        with top_bar.canvas.before:
            self.top_bar_color = Color(rgba=(0.1, 0.1, 0.1, 1))
            top_bar_rect = Rectangle(pos=top_bar.pos, size=top_bar.size)
        top_bar.bind(pos=lambda obj, val: setattr(top_bar_rect, 'pos', val),
                     size=lambda obj, val: setattr(top_bar_rect, 'size', val))

        self.menu_btn = Button(text="←", font_name="Roboto", font_size="28sp", background_normal="",
                               background_color=(0, 0, 0, 0), size_hint=(0.15, 1))
        self.menu_btn.bind(on_press=self.go_back_home)
        self.title_label = Label(text="Упражнения", font_name="Roboto", bold=True, size_hint=(0.7, 1))
        self.edit_toggle_btn = Button(text="✏", font_size="20sp", background_normal="", background_color=(0, 0, 0, 0),
                                      size_hint=(0.15, 1))
        self.edit_toggle_btn.bind(on_press=self.toggle_edit_mode)

        top_bar.add_widget(self.menu_btn)
        top_bar.add_widget(self.title_label)
        top_bar.add_widget(self.edit_toggle_btn)
        content_box.add_widget(top_bar)

        scroll = ScrollView()
        self.exercises_box = BoxLayout(orientation="vertical", spacing=10, size_hint_y=None,
                                       padding=[16, 16, 16, dp(80)])
        self.exercises_box.bind(minimum_height=self.exercises_box.setter("height"))
        scroll.add_widget(self.exercises_box)
        content_box.add_widget(scroll)

        start_box = BoxLayout(size_hint=(1, None), height=dp(70), padding=[16, 10, 16, 10])
        self.start_btn = StyledButton(text="НАЧАТЬ ТРЕНИРОВКУ")
        self.start_btn.bind(on_press=self.start_workout)
        start_box.add_widget(self.start_btn)
        content_box.add_widget(start_box)

        root.add_widget(content_box)
        self.fab_btn = CircularFAB(pos_hint={'right': 0.95, 'y': 0.12})
        self.fab_btn.bind(on_press=self.create_exercise)
        root.add_widget(self.fab_btn)
        self.add_widget(root)

    def load_exercises(self):
        try:
            self.exercises_box.clear_widgets()
            if not self.program_id: return

            cur.execute("SELECT name FROM programs WHERE id=?", (self.program_id,))
            p_row = cur.fetchone()
            if p_row: self.title_label.text = p_row[0].upper()

            cur.execute(
                "SELECT id, name, sets, reps, weight FROM exercises WHERE program_id=? ORDER BY order_index ASC",
                (self.program_id,))
            exercises = cur.fetchall()
            for row in exercises:
                card = RoundedCRUDCard(
                    item_id=row[0],
                    title_text=row[1],
                    sub_text=f"{row[2]}х{row[3]} | {format_weight(row[4])} кг",
                    edit_callback=lambda x, eid=row[0]: self.edit_exercise(eid),
                    delete_callback=lambda x, eid=row[0]: self.delete_exercise(eid),
                    click_callback=lambda x, eid=row[0]: self.edit_exercise(eid),
                    reorder_callback=self.save_exercise_order
                )
                card.toggle_edit(self.edit_mode)
                self.exercises_box.add_widget(card)
        except Exception as e:
            print("Load exercises error:", e)

    def save_exercise_order(self):
        try:
            for i, card in enumerate(reversed(self.exercises_box.children)):
                cur.execute("UPDATE exercises SET order_index=? WHERE id=?", (i, card.item_id))
            db.commit()
        except Exception as e:
            print("Save exercise order error:", e)

    def create_exercise(self, instance):
        app = App.get_running_app()
        layout = BoxLayout(orientation="vertical", spacing=app.spacing_compact, padding=app.pad_standard[0])
        n_in = TextInput(hint_text="Название", font_name="Roboto", multiline=False, size_hint_y=None,
                         height=app.height_input)
        s_in = TextInput(hint_text="Подходы", input_filter="int", font_name="Roboto", multiline=False, size_hint_y=None,
                         height=app.height_input)
        r_in = TextInput(hint_text="Повторения", input_filter="int", font_name="Roboto", multiline=False,
                         size_hint_y=None, height=app.height_input)
        w_in = TextInput(hint_text="Вес (кг)", input_filter="float", font_name="Roboto", multiline=False,
                         size_hint_y=None, height=app.height_input)

        save_btn = StyledButton(text="Добавить", size_hint_y=None, height=app.height_button)
        save_btn.bg_color_prop = app.primary_btn_color

        layout.add_widget(n_in);
        layout.add_widget(s_in);
        layout.add_widget(r_in);
        layout.add_widget(w_in)
        layout.add_widget(save_btn)

        popup = AppBaseModalView(size_hint=(0.85, 0.55))

        def save(inst):
            cur.execute("SELECT MAX(order_index) FROM exercises WHERE program_id=?", (self.program_id,))
            max_order = cur.fetchone()[0]
            next_order = 0 if max_order is None else max_order + 1
            cur.execute("INSERT INTO exercises(program_id, name, sets, reps, weight, order_index) VALUES(?,?,?,?,?,?)",
                        (self.program_id, n_in.text.strip() or "Без имени", int(s_in.text or 0), int(r_in.text or 0),
                         float(w_in.text or 0), next_order))
            db.commit()
            popup.dismiss()
            self.load_exercises()

        save_btn.bind(on_press=save)
        popup.add_widget(layout)
        popup.open()

    def edit_exercise(self, exercise_id):
        app = App.get_running_app()
        cur.execute("SELECT name, sets, reps, weight FROM exercises WHERE id=?", (exercise_id,))
        row = cur.fetchone()

        layout = BoxLayout(orientation="vertical", spacing=app.spacing_compact, padding=app.pad_standard[0])
        n_in = TextInput(text=row[0], font_name="Roboto", multiline=False, size_hint_y=None, height=app.height_input)
        s_in = TextInput(text=str(row[1]), input_filter="int", font_name="Roboto", multiline=False, size_hint_y=None,
                         height=app.height_input)
        r_in = TextInput(text=str(row[2]), input_filter="int", font_name="Roboto", multiline=False, size_hint_y=None,
                         height=app.height_input)
        w_in = TextInput(text=format_weight(row[3]), input_filter="float", font_name="Roboto", multiline=False,
                         size_hint_y=None, height=app.height_input)

        save_btn = StyledButton(text="Обновить", size_hint_y=None, height=app.height_button)
        save_btn.bg_color_prop = app.primary_btn_color

        layout.add_widget(n_in);
        layout.add_widget(s_in);
        layout.add_widget(r_in);
        layout.add_widget(w_in)
        layout.add_widget(save_btn)

        popup = AppBaseModalView(size_hint=(0.85, 0.55))

        def save(inst):
            cur.execute("UPDATE exercises SET name=?, sets=?, reps=?, weight=? WHERE id=?",
                        (n_in.text.strip() or "Без имени", int(s_in.text or 0), int(r_in.text or 0),
                         float(w_in.text or 0), exercise_id))
            db.commit()
            popup.dismiss()
            self.load_exercises()

        save_btn.bind(on_press=save)
        popup.add_widget(layout)
        popup.open()

    def delete_exercise(self, eid):
        cur.execute("DELETE FROM exercises WHERE id=?", (eid,))
        db.commit()
        self.load_exercises()

    def start_workout(self, instance):
        if not self.program_id: return
        app = App.get_running_app()
        cur.execute(
            "SELECT id, program_id, name, sets, reps, weight FROM exercises WHERE program_id=? ORDER BY order_index ASC",
            (self.program_id,))
        exercises = cur.fetchall()
        if not exercises:
            err = AppBaseModalView(size_hint=(0.7, 0.3))
            err.add_widget(Label(text="Сначала добавьте упражнения!", color=(1, 0.3, 0.3, 1), bold=True))
            err.open()
            return

        multi_data = [{"program_id": self.program_id, "name": self.title_label.text, "queue": exercises, "curr_idx": 0}]
        player = self.manager.get_screen("player")
        player.load_multi_queue(multi_data)
        app.animate_screen_transition(self.manager, "player", "left")


# ---------------- 6. ЭКРАН ПЛЕЕРА ТРЕНИРОВКИ ----------------

class WorkoutPlayerScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.multi_data = []
        self.active_p_idx = 0
        self.build_ui()

    def on_pre_enter(self):
        self.apply_theme_styles()

    def apply_theme_styles(self):
        app = App.get_running_app()

        self.bg_color_ctx.rgba = app.bg_color
        self.top_bar_color.rgba = app.bg_color
        self.close_btn.color = app.text_color
        self.list_btn.color = app.text_color

        if hasattr(self, 'slide_refs'):
            for refs in self.slide_refs:
                refs['c_color'].rgba = app.card_color
                refs['ex_name'].color = app.text_color
                refs['p_bg_col'].rgba = app.menu_bg_color
                refs['p_fill_col'].rgba = app.primary_btn_color

                refs['btn_prev'].bg_color_prop = app.card_color
                refs['btn_skip'].bg_color_prop = app.card_color
                refs['btn_next'].bg_color_prop = app.primary_btn_color

                for b in [refs['sets'], refs['reps'], refs['weight']]:
                    b.bg_color.rgba = app.menu_bg_color
                    b.title_lbl.color = app.sub_text_color
                    b.val_lbl.color = app.text_color

    def build_ui(self):
        self.root_layout = FloatLayout()
        app = App.get_running_app()

        with self.canvas.before:
            self.bg_color_ctx = Color(rgba=(0, 0, 0, 1))
            self.bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda obj, val: setattr(self.bg_rect, 'pos', val),
                  size=lambda obj, val: setattr(self.bg_rect, 'size', val))

        self.content_box = BoxLayout(orientation="vertical", size_hint=(1, 1))

        top_bar = BoxLayout(orientation="horizontal", size_hint=(1, 0.1), padding=10)
        with top_bar.canvas.before:
            self.top_bar_color = Color(rgba=(0.1, 0.1, 0.1, 1))
            top_bar_rect = Rectangle(pos=top_bar.pos, size=top_bar.size)
        top_bar.bind(pos=lambda obj, val: setattr(top_bar_rect, 'pos', val),
                     size=lambda obj, val: setattr(top_bar_rect, 'size', val))

        self.close_btn = Button(text="←", font_name="Roboto", font_size="28sp", background_normal="",
                                background_color=(0, 0, 0, 0), size_hint=(0.15, 1))
        self.close_btn.bind(on_press=self.exit_player)
        self.title_lbl = Label(text="ТРЕНИРОВКА", font_name="Roboto", bold=True, size_hint=(0.7, 1))
        self.list_btn = Button(text="📜", font_name="Roboto", font_size="24sp", background_normal="",
                               background_color=(0, 0, 0, 0), size_hint=(0.15, 1))
        self.list_btn.bind(on_press=self.open_queue_sheet)

        top_bar.add_widget(self.close_btn)
        top_bar.add_widget(self.title_lbl)
        top_bar.add_widget(self.list_btn)
        self.content_box.add_widget(top_bar)

        self.prog_carousel = Carousel(direction='bottom', size_hint=(1, 0.9))
        self.prog_carousel.bind(index=self.on_slide_change)
        self.content_box.add_widget(self.prog_carousel)

        self.root_layout.add_widget(self.content_box)
        self.add_widget(self.root_layout)

    def load_multi_queue(self, multi_data):
        self.multi_data = multi_data
        self.prog_carousel.clear_widgets()
        self.slide_refs = []
        app = App.get_running_app()

        for p_idx, prog in enumerate(multi_data):
            slide = BoxLayout(orientation='vertical', padding=20, spacing=20)

            prog_lbl = Label(text="Упражнение X из Y", font_name="Roboto", size_hint_y=0.1, color=(0.5, 0.5, 0.5, 1))
            slide.add_widget(prog_lbl)

            card = BoxLayout(orientation='vertical', padding=24, spacing=20, size_hint_y=0.6)
            with card.canvas.before:
                c_color = Color(rgba=app.card_color)
                c_rect = RoundedRectangle(radius=[dp(24)])
            card.bind(pos=lambda obj, val, r=c_rect: setattr(r, 'pos', val),
                      size=lambda obj, val, r=c_rect: setattr(r, 'size', val))

            ex_name = Label(text="Название", font_name="Roboto", font_size='28sp', bold=True, halign='center',
                            valign='middle', color=app.text_color)
            ex_name.bind(size=lambda inst, val: setattr(inst, 'text_size', val))

            stats_box = BoxLayout(orientation='horizontal', spacing=dp(15), size_hint_y=0.3)
            b_sets = StatBadge("ПОДХОДЫ")
            b_reps = StatBadge("ПОВТОРЫ")
            b_weight = StatBadge("ВЕС (КГ)")
            stats_box.add_widget(b_sets)
            stats_box.add_widget(b_reps)
            stats_box.add_widget(b_weight)

            card.add_widget(ex_name)
            card.add_widget(stats_box)

            prog_container = BoxLayout(size_hint=(1, None), height=dp(4), padding=[dp(20), 0, dp(20), 0])
            p_wid = Widget()
            with p_wid.canvas.before:
                p_bg_col = Color(rgba=app.menu_bg_color)
                p_bg = RoundedRectangle(radius=[dp(2)])
                p_fill_col = Color(rgba=app.primary_btn_color)
                p_fill = RoundedRectangle(radius=[dp(2)])

            def upd_p(inst, val, br=p_bg, fr=p_fill, c_idx=p_idx):
                br.pos = inst.pos
                br.size = inst.size
                q_len = len(self.multi_data[c_idx]["queue"])
                ratio = (self.multi_data[c_idx]["curr_idx"] + 1) / q_len if q_len > 0 else 0
                fr.pos = inst.pos
                fr.size = (inst.width * ratio, inst.height)

            p_wid.bind(pos=upd_p, size=upd_p)
            prog_container.add_widget(p_wid)
            card.add_widget(prog_container)

            slide.add_widget(card)

            swipe_lbl = Label(text="Свайп ↑/↓ сменить программу | Свайп ←/→ упражнение", font_size='12sp',
                              size_hint_y=0.05, color=(0.5, 0.5, 0.5, 1))
            slide.add_widget(swipe_lbl)

            nav_box = BoxLayout(orientation='horizontal', size_hint=(1, 0.15), padding=dp(16), spacing=dp(12))
            btn_skip = StyledButton(text="ПРОПУСК", size_hint=(0.28, 1))
            btn_skip.bg_color_prop = app.card_color
            btn_skip.bind(on_press=self.skip_step)

            btn_prev = StyledButton(text="НАЗАД", size_hint=(0.28, 1))
            btn_prev.bg_color_prop = app.card_color
            btn_prev.bind(on_press=self.prev_step)

            btn_next = StyledButton(text="ВЫПОЛНЕНО", size_hint=(0.44, 1))
            btn_next.bg_color_prop = app.primary_btn_color
            btn_next.bind(on_press=self.next_step)

            nav_box.add_widget(btn_skip)
            nav_box.add_widget(btn_prev)
            nav_box.add_widget(btn_next)
            slide.add_widget(nav_box)

            self.slide_refs.append({
                'prog_lbl': prog_lbl, 'ex_name': ex_name, 'sets': b_sets, 'reps': b_reps, 'weight': b_weight,
                'p_wid': p_wid, 'c_color': c_color, 'p_bg_col': p_bg_col, 'p_fill_col': p_fill_col,
                'btn_skip': btn_skip, 'btn_prev': btn_prev, 'btn_next': btn_next, 'upd_p': upd_p
            })
            self.prog_carousel.add_widget(slide)

        self.prog_carousel.index = 0
        self.active_p_idx = 0
        self.update_player_ui()

    def on_slide_change(self, instance, value):
        self.active_p_idx = value
        self.update_player_ui()

    def update_player_ui(self):
        if not self.multi_data or self.active_p_idx >= len(self.slide_refs): return

        prog = self.multi_data[self.active_p_idx]
        queue = prog["queue"]
        idx = prog["curr_idx"]

        self.title_lbl.text = f"{prog['name'].upper()} ({self.active_p_idx + 1}/{len(self.multi_data)})"

        total = len(queue)
        refs = self.slide_refs[self.active_p_idx]
        refs['prog_lbl'].text = f"Упражнение {idx + 1} из {total}"

        if total > 0:
            ex = queue[idx]
            refs['ex_name'].text = ex[2].upper()
            refs['sets'].set_val(str(ex[3]))
            refs['reps'].set_val(str(ex[4]))
            refs['weight'].set_val(format_weight(ex[5]))
        else:
            refs['ex_name'].text = "Пусто"

        if idx == total - 1:
            if self.active_p_idx == len(self.multi_data) - 1:
                refs['btn_next'].text = "ЗАВЕРШИТЬ ВСЁ 🎉"
            else:
                refs['btn_next'].text = "СЛЕДУЮЩАЯ ТРЕН. ↓"
            refs['btn_skip'].opacity = 0
            refs['btn_skip'].disabled = True
        else:
            refs['btn_next'].text = "ВЫПОЛНЕНО"
            refs['btn_skip'].opacity = 1
            refs['btn_skip'].disabled = False

        refs['upd_p'](refs['p_wid'], refs['p_wid'].size)

    def on_touch_down(self, touch):
        self.touch_x = touch.x
        self.touch_y = touch.y
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if hasattr(self, 'touch_x'):
            dx = touch.x - self.touch_x
            dy = touch.y - self.touch_y
            if abs(dx) > abs(dy) and abs(dx) > 50:
                if dx < -50:
                    self.next_step(None)
                elif dx > 50:
                    self.prev_step(None)
                return True
        return super().on_touch_up(touch)

    def skip_step(self, instance):
        prog = self.multi_data[self.active_p_idx]
        idx = prog["curr_idx"]
        if idx < len(prog["queue"]) - 1:
            prog["queue"][idx], prog["queue"][idx + 1] = prog["queue"][idx + 1], prog["queue"][idx]
            self.update_player_ui()

    def next_step(self, instance):
        prog = self.multi_data[self.active_p_idx]
        if prog["curr_idx"] < len(prog["queue"]) - 1:
            prog["curr_idx"] += 1
            self.update_player_ui()
        else:
            if self.active_p_idx < len(self.multi_data) - 1:
                self.prog_carousel.load_next()
            else:
                self.complete_workout()

    def prev_step(self, instance):
        prog = self.multi_data[self.active_p_idx]
        if prog["curr_idx"] > 0:
            prog["curr_idx"] -= 1
            self.update_player_ui()
        else:
            if self.active_p_idx > 0:
                self.prog_carousel.load_previous()

    def open_queue_sheet(self, instance):
        app = App.get_running_app()
        sheet = AppBaseBottomSheet(height_ratio=0.75)

        layout = BoxLayout(orientation='vertical', padding=dp(15), spacing=dp(10))
        layout.add_widget(DragHandle())

        prog = self.multi_data[self.active_p_idx]

        header_box = BoxLayout(orientation='horizontal', size_hint_y=0.1)
        title_lbl = Label(text=f"План: {prog['name']}", font_name="Roboto", bold=True, color=app.text_color,
                          halign="left", valign="middle")
        title_lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', val))

        close_btn = Button(text="✕", font_name="Roboto", font_size="24sp", background_normal="",
                           background_color=(0, 0, 0, 0), color=app.text_color, size_hint_x=None, width=dp(40))
        close_btn.bind(on_press=sheet.dismiss)

        header_box.add_widget(title_lbl)
        header_box.add_widget(close_btn)
        layout.add_widget(header_box)

        scroll = ScrollView()
        ex_box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)
        ex_box.bind(minimum_height=ex_box.setter('height'))

        for i, ex in enumerate(prog["queue"]):
            is_current = (i == prog["curr_idx"])
            bg_color = app.primary_btn_color if is_current else app.bg_color
            ex_text = f"{'▶ ' if is_current else ''}{ex[2]} | {ex[3]}x{ex[4]} | {format_weight(ex[5])} кг"

            btn = StyledButton(text=ex_text, size_hint_y=None, height=dp(50))
            btn.bg_color_prop = bg_color
            btn.color = get_contrast_color(bg_color) if is_current else app.text_color
            btn.halign = 'left'
            btn.valign = 'middle'
            btn.bind(size=lambda inst, val: setattr(inst, 'text_size', (val[0] - dp(20), val[1])))

            def jump(inst, idx=i):
                prog["curr_idx"] = idx
                self.update_player_ui()
                sheet.dismiss()

            btn.bind(on_press=jump)
            ex_box.add_widget(btn)

        scroll.add_widget(ex_box)
        layout.add_widget(scroll)
        sheet.add_widget(layout)
        sheet.open()

    def complete_workout(self):
        try:
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            total_vol = 0

            for prog in self.multi_data:
                pid = prog["program_id"]
                cur.execute("DELETE FROM calendar WHERE date=? AND program_id=?", (today_str, pid))
                cur.execute("INSERT INTO calendar(date, program_id, status) VALUES(?,?,?)",
                            (today_str, pid, 'completed'))

                vol = sum([float(ex[5] or 0) * int(ex[3] or 0) * int(ex[4] or 0) for ex in prog["queue"]])
                total_vol += vol

            App.get_running_app().pet.add_xp(total_vol)
            db.commit()

            home = self.manager.get_screen("home")
            home.populate_calendar()
            home.carousel.load_slide(home.carousel.slides[1])
            App.get_running_app().animate_screen_transition(self.manager, "home", "right")
        except Exception as e:
            print("Complete workout error:", e)

    def exit_player(self, instance):
        home = self.manager.get_screen("home")
        home.carousel.load_slide(home.carousel.slides[1])
        App.get_running_app().animate_screen_transition(self.manager, "home", "right")


# ---------------- 7. APP И МЕНЕДЖЕР ТЕМ (УНИФИЦИРОВАННОЕ ЯДРО) ----------------

class FitnessApp(App):
    bg_color = ListProperty([0, 0, 0, 1])
    card_color = ListProperty([0, 0, 0, 1])
    menu_bg_color = ListProperty([0, 0, 0, 1])
    text_color = ListProperty([1, 1, 1, 1])
    sub_text_color = ListProperty([0.6, 0.6, 0.6, 1])
    primary_btn_color = ListProperty([0.86, 0.08, 0.24, 1])
    secondary_btn_color = ListProperty([0.5, 0.05, 0.15, 1])

    radius_card = NumericProperty(dp(16))
    radius_button = NumericProperty(dp(10))
    radius_small = NumericProperty(dp(8))

    pad_standard = ListProperty([dp(16), dp(16), dp(16), dp(16)])
    pad_compact = ListProperty([dp(10), dp(10), dp(10), dp(10)])
    spacing_standard = NumericProperty(dp(12))
    spacing_compact = NumericProperty(dp(6))

    height_button = NumericProperty(dp(50))
    height_input = NumericProperty(dp(45))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.base_mode = "dark"
        self.accent_mode = "crimson"
        self.custom_hex = "#DC143C"
        self.update_theme_colors()

    def animate_screen_transition(self, sm, target, direction='left'):
        sm.transition.direction = direction
        sm.current = target

    def animate_modal_toggle(self, modal, action='open'):
        if action == 'open':
            modal.open()
        else:
            modal.dismiss()

    def update_theme_colors(self):
        if self.base_mode == "dark":
            self.bg_color = get_color_from_hex("#0D0D11")
            self.card_color = get_color_from_hex("#16161F")
            self.menu_bg_color = get_color_from_hex("#1C1C26")
            self.text_color = get_color_from_hex("#FFFFFF")
            self.sub_text_color = get_color_from_hex("#A0A0A0")
        else:
            self.bg_color = get_color_from_hex("#F4F4F9")
            self.card_color = get_color_from_hex("#FFFFFF")
            self.menu_bg_color = get_color_from_hex("#EAEAEA")
            self.text_color = get_color_from_hex("#1A1A1A")
            self.sub_text_color = get_color_from_hex("#666666")

        if self.accent_mode == "crimson":
            self.primary_btn_color = get_color_from_hex("#DC143C")
            self.secondary_btn_color = get_color_from_hex("#8B0000")
        elif self.accent_mode == "sapphire":
            self.primary_btn_color = get_color_from_hex("#0F52BA")
            self.secondary_btn_color = get_color_from_hex("#002FA7")
        elif self.accent_mode == "neon":
            self.primary_btn_color = get_color_from_hex("#39FF14")
            self.secondary_btn_color = get_color_from_hex("#00FF00")
        elif self.accent_mode == "sunset":
            self.primary_btn_color = get_color_from_hex("#FF4500")
            self.secondary_btn_color = get_color_from_hex("#FF8C00")
        elif self.accent_mode == "violet":
            self.primary_btn_color = get_color_from_hex("#8A2BE2")
            self.secondary_btn_color = get_color_from_hex("#4B0082")
        elif self.accent_mode == "custom":
            self.primary_btn_color = get_color_from_hex(self.custom_hex)
            self.secondary_btn_color = get_color_from_hex("#333333")

    def refresh_all_screens(self):
        self.update_theme_colors()
        if hasattr(self, 'root') and self.root:
            home = self.root.get_screen("home")
            home.apply_theme_styles()
            home.populate_calendar()

            ex_scr = self.root.get_screen("exercises")
            ex_scr.on_pre_enter()

            pl_scr = self.root.get_screen("player")
            pl_scr.on_pre_enter()

    def open_theme_popup(self):
        sheet = AppBaseBottomSheet(height_ratio=0.7)
        layout = BoxLayout(orientation='vertical', padding=self.pad_standard[0], spacing=self.spacing_standard)

        layout.add_widget(DragHandle())
        layout.add_widget(
            Label(text="РЕЖИМ ОСНОВЫ", font_name="Roboto", bold=True, size_hint_y=0.1, color=self.text_color))

        base_box = BoxLayout(orientation='horizontal', spacing=10, size_hint_y=0.12)
        btn_dark = StyledButton(text="ТЁМНЫЙ ПРЕМИУМ")
        btn_dark.bg_color_prop = self.primary_btn_color if self.base_mode == "dark" else self.card_color

        btn_light = StyledButton(text="СВЕТЛЫЙ ПРЕМИУМ")
        btn_light.bg_color_prop = self.primary_btn_color if self.base_mode == "light" else self.card_color

        def set_base(mode):
            self.base_mode = mode
            self.refresh_all_screens()

        btn_dark.bind(on_press=lambda x: set_base("dark"))
        btn_light.bind(on_press=lambda x: set_base("light"))
        base_box.add_widget(btn_dark);
        base_box.add_widget(btn_light)
        layout.add_widget(base_box)

        layout.add_widget(
            Label(text="АКЦЕНТЫ ИНТЕРФЕЙСА", font_name="Roboto", bold=True, size_hint_y=0.1, color=self.text_color))

        accents = [("КРИМЗОН", "crimson"), ("САПФИР", "sapphire"), ("НЕОН", "neon"), ("ЗАКАТ", "sunset"),
                   ("ФИОЛЕТ", "violet")]
        acc_grid = GridLayout(cols=3, spacing=10, size_hint_y=0.25)

        def set_accent(acc_m):
            self.accent_mode = acc_m
            self.refresh_all_screens()

        for label, mode in accents:
            b = Button(background_normal="", background_color=(0, 0, 0, 0))
            with b.canvas.before:
                Color(rgba=get_color_from_hex({
                                                  "crimson": "#DC143C", "sapphire": "#0F52BA", "neon": "#39FF14",
                                                  "sunset": "#FF4500", "violet": "#8A2BE2"
                                              }[mode]))
                Ellipse(pos=b.pos, size=b.size)
            b.bind(pos=lambda obj, val, c=b.canvas.before.children[-1]: setattr(c, 'pos', (obj.center_x - min(obj.width,
                                                                                                              obj.height) * 0.4,
                                                                                           obj.center_y - min(obj.width,
                                                                                                              obj.height) * 0.4)))
            b.bind(size=lambda obj, val, c=b.canvas.before.children[-1]: setattr(c, 'size',
                                                                                 (min(obj.width, obj.height) * 0.8,
                                                                                  min(obj.width, obj.height) * 0.8)))
            b.bind(on_press=lambda x, m=mode: set_accent(m))
            acc_grid.add_widget(b)

        btn_c = StyledButton(text="🎨")
        btn_c.bg_color_prop = self.card_color
        btn_c.bind(on_press=lambda x: self.open_custom_color_wheel(sheet))
        acc_grid.add_widget(btn_c)

        layout.add_widget(acc_grid)
        layout.add_widget(Label(size_hint_y=0.1))

        done_btn = StyledButton(text="ГОТОВО", size_hint_y=None, height=dp(55))
        done_btn.bg_color_prop = self.primary_btn_color
        self.bind(primary_btn_color=lambda inst, val: setattr(done_btn, 'bg_color_prop', val))
        done_btn.bind(on_press=sheet.dismiss)
        layout.add_widget(done_btn)

        sheet.add_widget(layout)
        sheet.open()

    def open_custom_color_wheel(self, parent_sheet):
        parent_sheet.dismiss()
        sheet = AppBaseBottomSheet(height_ratio=0.7)
        layout = BoxLayout(orientation='vertical', padding=self.pad_standard[0], spacing=self.spacing_standard)

        content = BoxLayout(orientation='vertical', size_hint_y=0.8, spacing=10)
        wheel = SmoothColorWheel(size_hint_y=0.7)
        slider = Slider(min=0.2, max=1.0, value=1.0, size_hint_y=0.1)

        def on_color_change(*args):
            try:
                h, s, v = wheel.current_hsv
                v = slider.value
                r, g, b = colorsys.hsv_to_rgb(h, s, v)
                self.accent_mode = "custom"
                self.custom_hex = f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"
                self.refresh_all_screens()
            except Exception:
                pass

        wheel.bind(on_color_change=on_color_change)
        slider.bind(value=on_color_change)

        content.add_widget(wheel);
        content.add_widget(slider)
        layout.add_widget(content)

        apply_b = StyledButton(text="ГОТОВО", size_hint_y=None, height=self.height_button)
        apply_b.bg_color_prop = self.primary_btn_color
        apply_b.bind(on_press=sheet.dismiss)
        layout.add_widget(apply_b)

        sheet.add_widget(layout)
        sheet.open()

    def open_pet_settings(self):
        sheet = AppBaseBottomSheet(height_ratio=0.85)
        layout = BoxLayout(orientation='vertical', padding=self.pad_standard[0], spacing=self.spacing_standard)

        layout.add_widget(DragHandle())
        layout.add_widget(
            Label(text="НАСТРОЙКИ ПИТОМЦА", font_name="Roboto", bold=True, size_hint_y=0.1, color=self.text_color))

        lvl = 1 + int(self.pet.total_xp // 1000)
        next_xp = lvl * 1000
        progress_text = f"Уровень: {lvl} | Опыт: {int(self.pet.total_xp)} / {next_xp} XP\nСытость/Счастье: {self.pet.happiness}%"
        layout.add_widget(
            Label(text=progress_text, font_name="Roboto", size_hint_y=0.15, color=self.sub_text_color, halign="center"))

        content = BoxLayout(orientation='vertical', spacing=10, size_hint_y=0.6)
        content.add_widget(
            Label(text="Выбери персонажа:", font_name="Roboto", bold=True, size_hint_y=0.1, color=self.text_color,
                  halign="left"))

        types_box = BoxLayout(orientation='horizontal', spacing=10, size_hint_y=0.15)
        for p_name, p_file in [("Спанч Боб", "spongebob.png"), ("Патрик", "patrick.png"), ("Гэри", "gary.png")]:
            b = StyledButton(text=p_name)
            b.bg_color_prop = self.primary_btn_color if self.pet.p_type == p_file else self.card_color

            def set_p(inst, fname=p_file):
                self.pet.p_type = fname
                self.pet.save_settings()
                self.pet.update_visual()
                sheet.dismiss()

            b.bind(on_press=set_p)
            types_box.add_widget(b)
        content.add_widget(types_box)

        content.add_widget(Label(text="Ограничить внизу экрана:", font_name="Roboto", bold=True, size_hint_y=0.1,
                                 color=self.text_color, halign="left"))
        btn_bot = StyledButton(text="Включено" if self.pet.bottom_only else "Отключено", size_hint_y=0.1)
        btn_bot.bg_color_prop = self.primary_btn_color if self.pet.bottom_only else self.card_color

        def toggle_bot(inst):
            self.pet.bottom_only = not self.pet.bottom_only
            self.pet.save_settings()

            if self.pet.bottom_only and self.pet.y > dp(150):
                Animation(y=dp(50), duration=0.5, t='out_bounce').start(self.pet)

            inst.text = "Включено" if self.pet.bottom_only else "Отключено"
            inst.bg_color_prop = self.primary_btn_color if self.pet.bottom_only else self.card_color

        btn_bot.bind(on_press=toggle_bot)
        content.add_widget(btn_bot)

        content.add_widget(
            Label(text="Бессмертие (Не падает счастье):", font_name="Roboto", bold=True, size_hint_y=0.1,
                  color=self.text_color, halign="left"))
        btn_imm = StyledButton(text="Активно" if self.pet.immortal else "Неактивно", size_hint_y=0.1)
        btn_imm.bg_color_prop = self.primary_btn_color if self.pet.immortal else self.card_color

        def toggle_immortal(inst):
            self.pet.immortal = not self.pet.immortal
            self.pet.save_settings()
            inst.text = "Активно" if self.pet.immortal else "Неактивно"
            inst.bg_color_prop = self.primary_btn_color if self.pet.immortal else self.card_color

        btn_imm.bind(on_press=toggle_immortal)
        content.add_widget(btn_imm)

        content.add_widget(
            Label(text="Отключить питомца:", font_name="Roboto", bold=True, size_hint_y=0.1, color=self.text_color,
                  halign="left"))
        btn_dis = StyledButton(text="Скрыт" if self.pet.disabled_pet else "Отображается", size_hint_y=0.1)
        btn_dis.bg_color_prop = (1, 0.2, 0.2, 1) if self.pet.disabled_pet else self.card_color

        def toggle_disabled(inst):
            self.pet.disabled_pet = not self.pet.disabled_pet
            self.pet.save_settings()
            self.pet.update_visual()
            inst.text = "Скрыт" if self.pet.disabled_pet else "Отображается"
            inst.bg_color_prop = (1, 0.2, 0.2, 1) if self.pet.disabled_pet else self.card_color

        btn_dis.bind(on_press=toggle_disabled)
        content.add_widget(btn_dis)

        content.add_widget(
            Label(text="Размер:", font_name="Roboto", bold=True, size_hint_y=0.1, color=self.text_color, halign="left"))
        sz_slider = Slider(min=60, max=180, value=self.pet.size[0] / dp(1), size_hint_y=0.1)

        def on_sz(*a):
            new_sz = dp(sz_slider.value)
            self.pet.size_hint = (None, None)
            self.pet.size = (new_sz, new_sz)
            self.pet.chat_label.font_size = f"{sz_slider.value * 0.2}sp"

            max_y = dp(150) if self.pet.bottom_only else max(0, Window.height - self.pet.height)
            if self.pet.y > max_y: self.pet.y = max_y
            if self.pet.x > Window.width - self.pet.width: self.pet.x = Window.width - self.pet.width
            self.pet.save_settings()

        sz_slider.bind(value=on_sz)
        content.add_widget(sz_slider)

        layout.add_widget(content)

        done_btn = StyledButton(text="ГОТОВО", size_hint_y=None, height=self.height_button)
        done_btn.bg_color_prop = self.primary_btn_color
        self.bind(primary_btn_color=lambda inst, val: setattr(done_btn, 'bg_color_prop', val))
        done_btn.bind(on_press=sheet.dismiss)
        layout.add_widget(done_btn)

        sheet.add_widget(layout)
        sheet.open()

    def build(self):
        self.sm = ScreenManager(transition=SlideTransition(duration=0.25))

        self.pet = LivePetWidget()

        self.sm.add_widget(HomeScreen(name="home"))
        self.sm.add_widget(ExercisesScreen(name="exercises"))
        self.sm.add_widget(WorkoutPlayerScreen(name="player"))

        root = FloatLayout()
        root.add_widget(self.sm)
        root.add_widget(self.pet)

        return root


if __name__ == "__main__":
    FitnessApp().run()