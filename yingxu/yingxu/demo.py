"""Explicit, synthetic sample project — never scans the user's existing library."""
from pathlib import Path
import shutil
from .runtime import ffmpeg_path
import subprocess


def create_demo(store):
    name='雾港来信 · 示例项目'
    for p in store.list_projects():
        if p['name']==name:return p
    project=store.create_project(name,'一个用于熟悉工作台的虚构短片项目。所有文字、构图与视频均为示例；可放心编辑，未导入你的真实素材。')
    pid=project['id']
    def add(category,name,content,status='待开始',tags=None,metadata=None):
        return store.create_item({'project_id':pid,'category':category,'name':name,'content':content,'status':status,'tags':tags or [],'metadata':metadata or {}})
    script=add('scripts','01_剧本 · 雾港来信','# 雾港来信\n\n> 示例项目 · 三分钟氛围短片\n\n## 故事梗概\n\n一名修复旧录音机的年轻人，在凌晨的港口收到一封写给未来的信。天亮之前，她必须决定是否按下播放键。\n\n## 第一场 · 港口外景 · 黎明前\n\n潮水漫过石阶。远处灯塔每隔五秒扫过雾面。\n\n**林岚**站在锈蚀的扶栏旁，捏着一封没有署名的信。\n\n林岚：如果这封信真的来自明天，你为什么现在才告诉我？\n\n## 第二场 · 修理铺内景\n\n旧磁带缓缓转动。窗外的灯光投下细长的矩形。\n\n## 创作备忘\n\n- [x] 故事概念与世界设定\n- [ ] 第一轮白模预演\n- [ ] 角色一致性参考\n- [ ] 镜头生成与审核\n\n可以修改这里的文字，按 Ctrl+S 保存。\n','进行中',['主剧本'])
    character=add('characters','林岚 · 角色设定','# 林岚\n\n## 角色定位\n\n27岁，旧录音机修复师。行动克制，对声音极为敏感。\n\n## 外形一致性\n\n灰绿色短外套、浅色内搭、短发。左手戴一只旧表。\n\n## 表演关键词\n\n停顿、侧耳、欲言又止。\n\n## 素材位置\n\n将角色图导入“角色”，再通过右侧关联与本设定或分镜连接。\n','已完成',['主角','林岚'])
    scene=add('scenes','雾港 · 场景设定','# 雾港\n\n## 空间基准\n\n画面左侧灯塔，右侧旧修理铺，中央石阶通向水面。\n\n## 光线\n\n黎明前的青灰色环境光，灯塔为暖白扫光。\n\n## 连续性\n\n风从画面左侧吹来，雨后地面湿润。\n','已完成',['外景','雾','港口'])
    prop=add('props','无署名信封 · 道具','# 无署名信封\n\n米白色粗纹纸，边角受潮，正面只有手写的“林岚”。\n\n道具在镜头 02 与 03 中保持相同折痕。\n','待审核',['信封','关键道具'])
    shot_data=[('01','雾中的港口','建立空间，灯塔扫光穿过雾层。','大全景','缓慢前推','进行中'),('02','一封没有署名的信','林岚低头查看手中的信，拇指停在封口。','近景','固定镜头','待审核'),('03','播放键前的停顿','手指悬停在播放键上，远处传来一声船笛。','特写','极慢推近','待开始')]
    shots=[]
    for number,title,action,size,camera,status in shot_data:
        shot=add('shots',f'{number} · {title}',f'# 镜头 {number} · {title}\n\n## 画面\n\n{action}\n\n## 声音\n\n低沉的海风、细碎的机械声。\n\n## 生成提示词\n\n青灰色黎明，克制的暖光，写实电影质感，保持空间连续性。\n\n## 下一步\n\n先确认白模构图，再开始最终画面生成。\n',status,['第一场','示例'],{'shot_number':number,'duration':5,'shot_size':size,'camera':camera,'prompt':action+' 青灰色黎明，暖白灯塔光，电影构图。','version':'v01'})
        store.add_relation(shot['id'],scene['id'],'场景');store.add_relation(shot['id'],script['id'],'所属剧本')
        if number!='01':store.add_relation(shot['id'],character['id'],'角色')
        if number=='02':store.add_relation(shot['id'],prop['id'],'道具')
        shots.append(shot)
    add('delivery','交付检查表','# 交付检查表\n\n- [ ] 画面与对白连续性\n- [ ] 角色与道具一致性\n- [ ] 所有镜头已审核\n- [ ] 音频、字幕和画面同步\n- [ ] 导出母版与分享版\n\n将确定采用的成片导入这里。\n',tags=['交付'])
    add('references','使用这份示例','# 这是一份可编辑的示例\n\n1. 左侧选择不同素材分类。\n2. 打开剧本，在编辑区修改文字。\n3. 打开分镜，查看右侧关联角色、场景与道具。\n4. 新建自己的项目，再导入真实素材。\n\n构图图像为几何示意，预演视频为平面构图动画，不是完成的电影或真实三维模型。\n')
    # Diagram-like sample frames drawn from code, not scraped/user images.
    root=Path(project['root']);folder=root/'40_Runs/白模预演';media=[]
    try:
        from PIL import Image,ImageDraw
        for i in range(3):
            im=Image.new('RGB',(1280,720),(36+8*i,44+5*i,45+4*i));d=ImageDraw.Draw(im)
            for y in range(720):
                shade=int(y/720*18);d.line([(0,y),(1280,y)],fill=(41+shade+i*6,50+shade,52+shade))
            d.ellipse((760-i*140,100,875-i*140,215),fill=(205,205,184))
            d.polygon([(0,490),(1280,400),(1280,720),(0,720)],fill=(66,72,70))
            for j in range(7):
                x=120+j*164-i*28;h=80+(j%3)*46
                d.polygon([(x,520),(x,520-h),(x+70,497-h),(x+70,497)],fill=(169,176,171))
                d.polygon([(x+70,497-h),(x+103,515-h),(x+103,535),(x+70,497)],fill=(106,119,115))
                d.polygon([(x,520-h),(x+34,494-h),(x+103,515-h),(x+70,497-h)],fill=(202,204,192))
            d.line([(0,550),(1280,420)],fill=(191,185,163),width=2)
            d.rectangle((40,40,1240,680),outline=(121,135,126),width=2)
            path=folder/f'镜头0{i+1}_白模构图示例.png';im.save(path);media.append(path)
        ffmpeg=ffmpeg_path()
        if ffmpeg:
            video=folder/'镜头01_平面预演示例.mp4'
            subprocess.run([ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-loop','1','-i',str(media[0]),'-vf','scale=960:540','-t','4','-r','24','-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-movflags','+faststart','-y',str(video)],check=True,timeout=30,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            media.append(video)
        source=next(s for s in store.sources(pid) if s['path']==str(root))
        store.index_files(source,media)
        with store.connection() as db:
            media_rows=db.execute("SELECT id,name FROM items WHERE project_id=? AND category='previs'",(pid,)).fetchall()
        for row in media_rows:
            number=2 if '03' in row['name'] else 1 if '02' in row['name'] else 0
            store.add_relation(shots[number]['id'],row['id'],'白模参考')
    except (ImportError,OSError,subprocess.SubprocessError):pass
    return store.get_project(pid)
