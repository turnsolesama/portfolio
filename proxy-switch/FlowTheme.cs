using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace FlowSwitch.UI
{
    public static class Palette
    {
        public static readonly Color Canvas = ColorTranslator.FromHtml("#14171C");
        public static readonly Color Surface = ColorTranslator.FromHtml("#1C2027");
        public static readonly Color Raised = ColorTranslator.FromHtml("#282E38");
        public static readonly Color Border = ColorTranslator.FromHtml("#39424F");
        public static readonly Color Text = ColorTranslator.FromHtml("#EDF0F5");
        public static readonly Color Muted = ColorTranslator.FromHtml("#ADB6C4");
        public static readonly Color Accent = ColorTranslator.FromHtml("#ACC8F0");
        public static GraphicsPath Round(Rectangle rect, int radius)
        {
            var p = new GraphicsPath(); int d = Math.Min(radius * 2, Math.Min(rect.Width, rect.Height));
            p.AddArc(rect.Left, rect.Top, d, d, 180, 90); p.AddArc(rect.Right-d, rect.Top, d, d, 270, 90);
            p.AddArc(rect.Right-d, rect.Bottom-d, d, d, 0, 90); p.AddArc(rect.Left, rect.Bottom-d, d, d, 90, 90); p.CloseFigure(); return p;
        }
        public static void Apply(Control root)
        {
            root.ForeColor = Text;
            foreach(Control c in root.Controls)
            {
                if(c is TextBox || c is ComboBox) { c.BackColor=Raised; c.ForeColor=Text; }
                else if(c is CheckBox) c.ForeColor=Muted;
                ApplyChildren(c);
            }
        }
        private static void ApplyChildren(Control c)
        {
            foreach(Control child in c.Controls)
            {
                if(child is TextBox || child is ComboBox) { child.BackColor=Raised; child.ForeColor=Text; }
                else if(child is CheckBox) child.ForeColor=Muted;
                ApplyChildren(child);
            }
        }
    }
    public sealed class SurfacePanel : Panel
    {
        public SurfacePanel() { DoubleBuffered=true;SetStyle(ControlStyles.ResizeRedraw,true); BackColor=Palette.Surface; }
        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.SmoothingMode=SmoothingMode.AntiAlias;
            e.Graphics.Clear(Parent==null ? Palette.Canvas : Parent.BackColor);
            using(var path=Palette.Round(new Rectangle(0,0,Width-1,Height-1),12))
            using(var brush=new SolidBrush(BackColor))
            using(var pen=new Pen(Palette.Border)) { e.Graphics.FillPath(brush,path); e.Graphics.DrawPath(pen,path); }
            base.OnPaint(e);
        }
    }
    public sealed class ActionButton : Button
    {
        private bool over, down;
        public bool Primary {get;set;}
        public bool Selected {get;set;}
        public bool Navigation {get;set;}
        public ActionButton() { DoubleBuffered=true; FlatStyle=FlatStyle.Flat; FlatAppearance.BorderSize=0; UseVisualStyleBackColor=false; BackColor=Palette.Raised; ForeColor=Palette.Text; }
        protected override void OnMouseEnter(EventArgs e){over=true;Invalidate();base.OnMouseEnter(e);}
        protected override void OnMouseLeave(EventArgs e){over=false;down=false;Invalidate();base.OnMouseLeave(e);}
        protected override void OnMouseDown(MouseEventArgs e){down=true;Invalidate();base.OnMouseDown(e);}
        protected override void OnMouseUp(MouseEventArgs e){down=false;Invalidate();base.OnMouseUp(e);}
        protected override void OnEnabledChanged(EventArgs e){Invalidate();base.OnEnabledChanged(e);}
        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.SmoothingMode=SmoothingMode.AntiAlias; e.Graphics.Clear(Parent==null ? Palette.Canvas : Parent.BackColor);
            Color fill=Primary?Palette.Accent:(Selected?ColorTranslator.FromHtml("#2B394D"):BackColor);
            if(over && Enabled) fill=ControlPaint.Light(fill,0.12f);
            if(down && Enabled) fill=ControlPaint.Dark(fill,0.1f);
            if(!Enabled) fill=Palette.Surface;
            using(var path=Palette.Round(new Rectangle(0,0,Width-1,Height-1),8))
            using(var brush=new SolidBrush(fill))
            using(var pen=new Pen(Focused?Palette.Accent:(Primary || Selected?fill:Palette.Border),Focused?2:1))
            { e.Graphics.FillPath(brush,path);e.Graphics.DrawPath(pen,path); }
            var textColor=!Enabled?Palette.Muted:(Primary?ColorTranslator.FromHtml("#172333"):(Selected?Palette.Accent:ForeColor));
            var flags=TextFormatFlags.VerticalCenter|TextFormatFlags.EndEllipsis|TextFormatFlags.SingleLine;
            flags|=Navigation?TextFormatFlags.Left:TextFormatFlags.HorizontalCenter;
            TextRenderer.DrawText(e.Graphics,Text,Font,new Rectangle(Navigation?16:7,0,Width-(Navigation?28:14),Height),textColor,flags);
        }
    }
    public sealed class PageHost : TabControl
    {
        public PageHost(){SetStyle(ControlStyles.OptimizedDoubleBuffer,true);}
        public override Rectangle DisplayRectangle {get{return ClientRectangle;}}
        protected override void WndProc(ref Message m){if(m.Msg==0x1328){m.Result=new IntPtr(1);return;}base.WndProc(ref m);}
    }
    public sealed class RouteChoice : ComboBox
    {
        public RouteChoice(){DrawMode=DrawMode.OwnerDrawFixed;ItemHeight=27;FlatStyle=FlatStyle.Flat;BackColor=Palette.Raised;ForeColor=Palette.Text;}
        protected override void OnDrawItem(DrawItemEventArgs e)
        {
            Color fill=(e.State&DrawItemState.Selected)!=0?ColorTranslator.FromHtml("#30415A"):Palette.Raised;
            using(var b=new SolidBrush(fill))e.Graphics.FillRectangle(b,e.Bounds);
            string text=e.Index>=0?GetItemText(Items[e.Index]):Text;
            TextRenderer.DrawText(e.Graphics,text,Font,new Rectangle(e.Bounds.X+8,e.Bounds.Y,e.Bounds.Width-12,e.Bounds.Height),Palette.Text,TextFormatFlags.VerticalCenter|TextFormatFlags.EndEllipsis|TextFormatFlags.SingleLine);
        }
        protected override void WndProc(ref Message m)
        {
            base.WndProc(ref m);
            if((m.Msg==0x000F || m.Msg==0x0317) && IsHandleCreated)
            using(var g=m.Msg==0x0317?Graphics.FromHdc(m.WParam):CreateGraphics())
            using(var b=new SolidBrush(Palette.Raised))
            using(var pen=new Pen(Focused?Palette.Accent:Palette.Border))
            {
                g.FillRectangle(b,0,0,Width,Height);g.DrawRectangle(pen,0,0,Width-1,Height-1);
                TextRenderer.DrawText(g,SelectedIndex>=0?GetItemText(SelectedItem):Text,Font,new Rectangle(8,0,Width-36,Height),Palette.Text,TextFormatFlags.VerticalCenter|TextFormatFlags.SingleLine|TextFormatFlags.EndEllipsis);
                using(var arrow=new SolidBrush(Palette.Muted))g.FillPolygon(arrow,new[]{new Point(Width-16,Height/2-2),new Point(Width-8,Height/2-2),new Point(Width-12,Height/2+2)});
            }
        }
    }
    public sealed class DataList : ListView
    {
        private readonly ImageList spacing;
        private HeaderPainter header;
        private double[] weights;
        private bool sizing;
        public void SetColumnWeights(double[] values) { weights=values;FitColumns(); }
        private void FitColumns()
        {
            if(sizing || weights==null || Columns.Count!=weights.Length || Width<100)return;
            sizing=true;
            try {
                // Use the real client and clipped viewport, including native DPI and scrollbar metrics.
                int available=Math.Max(1,Math.Min(ClientSize.Width,Parent==null?ClientSize.Width:Parent.ClientSize.Width)-2),used=0;
                for(int i=0;i<Columns.Count;i++) {
                    int width=i==Columns.Count-1?available-used:(int)Math.Floor(available*weights[i]);
                    if(Columns[i].Width!=width)Columns[i].Width=width;
                    used+=width;
                }
            } finally {sizing=false;}
        }
        protected override void OnSizeChanged(EventArgs e){base.OnSizeChanged(e);FitColumns();}
        protected override void ScaleControl(SizeF factor,BoundsSpecified specified){base.ScaleControl(factor,specified);FitColumns();}
        protected override void OnColumnWidthChanging(ColumnWidthChangingEventArgs e)
        {
            base.OnColumnWidthChanging(e);
            if(weights!=null){e.NewWidth=Columns[e.ColumnIndex].Width;e.Cancel=true;}
        }
        protected override void WndProc(ref Message m)
        {
            // Native column scaling/EnsureVisible may run after SizeChanged. Repair before any frame is drawn.
            if(m.Msg==0xF || m.Msg==0x85 || m.Msg==0x317)FitColumns();
            base.WndProc(ref m);
            if(Parent!=null && Parent.Parent is ScrollHost)((ScrollHost)Parent.Parent).RefreshScroll();
        }
        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern IntPtr SendMessage(IntPtr hwnd,uint message,IntPtr w,IntPtr l);
        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e); var hwnd=SendMessage(Handle,0x101F,IntPtr.Zero,IntPtr.Zero);
            if(hwnd!=IntPtr.Zero){header=new HeaderPainter(this);header.AssignHandle(hwnd);}
            FitColumns();
        }
        protected override void OnHandleDestroyed(EventArgs e){if(header!=null){header.ReleaseHandle();header=null;}base.OnHandleDestroyed(e);}
        private sealed class HeaderPainter : NativeWindow
        {
            private readonly DataList list;
            public HeaderPainter(DataList value){list=value;}
            protected override void WndProc(ref Message m)
            {
                base.WndProc(ref m);
                if((m.Msg==0x000F || m.Msg==0x0317) && Handle!=IntPtr.Zero)
                {
                    int width=0;foreach(ColumnHeader c in list.Columns)width+=c.Width;
                    if(width<list.ClientSize.Width)using(var g=m.Msg==0x0317?Graphics.FromHdc(m.WParam):Graphics.FromHwnd(Handle))using(var b=new SolidBrush(Palette.Raised))g.FillRectangle(b,width,0,list.ClientSize.Width-width,100);
                }
            }
        }
        public DataList()
        {
            DoubleBuffered=true;OwnerDraw=true;BackColor=Palette.Surface;ForeColor=Palette.Text;
            BorderStyle=BorderStyle.None; spacing=new ImageList();spacing.ImageSize=new Size(1,36);SmallImageList=spacing;
        }
        protected override void OnDrawColumnHeader(DrawListViewColumnHeaderEventArgs e)
        {
            using(var b=new SolidBrush(Palette.Raised))e.Graphics.FillRectangle(b,e.Bounds);
            TextRenderer.DrawText(e.Graphics,e.Header.Text,Font,new Rectangle(e.Bounds.X+12,e.Bounds.Y,e.Bounds.Width-16,e.Bounds.Height),Palette.Muted,TextFormatFlags.VerticalCenter|TextFormatFlags.Left|TextFormatFlags.EndEllipsis);
        }
        protected override void OnDrawItem(DrawListViewItemEventArgs e){if(View!=View.Details)e.DrawDefault=true;}
        protected override void OnDrawSubItem(DrawListViewSubItemEventArgs e)
        {
            bool selected=e.Item.Selected;
            Color fill=selected?ColorTranslator.FromHtml("#30415A"):(e.ItemIndex%2==0?Palette.Surface:ColorTranslator.FromHtml("#20252D"));
            using(var b=new SolidBrush(fill))e.Graphics.FillRectangle(b,e.Bounds);
            var color=selected || e.ColumnIndex<2?Palette.Text:e.Item.ForeColor;
            TextRenderer.DrawText(e.Graphics,e.SubItem.Text,Font,new Rectangle(e.Bounds.X+12,e.Bounds.Y,e.Bounds.Width-18,e.Bounds.Height),color,TextFormatFlags.VerticalCenter|TextFormatFlags.Left|TextFormatFlags.EndEllipsis|TextFormatFlags.SingleLine);
            if(e.ColumnIndex==0 && selected) using(var b=new SolidBrush(Palette.Accent))e.Graphics.FillRectangle(b,new Rectangle(e.Bounds.X,e.Bounds.Y+7,3,e.Bounds.Height-14));
        }
        protected override void Dispose(bool disposing){base.Dispose(disposing);if(disposing)spacing.Dispose();}
    }
    // The original control keeps its native scroll range and keyboard/wheel behavior.
    // Its scrollbar sits underneath a sibling rail; no system-wide theme or scroll settings change.
    public class ScrollHost : Panel
    {
        private readonly Panel viewport;
        public Control Content {get;private set;}
        public ScrollRail Rail {get;private set;}
        public ScrollHost(Control content) {
            DoubleBuffered=true;SetStyle(ControlStyles.ResizeRedraw,true);BackColor=Palette.Surface;Content=content;
            viewport=new Panel();viewport.BackColor=Palette.Surface;Controls.Add(viewport);
            Rail=new ScrollRail(content);viewport.Controls.Add(content);Controls.Add(Rail);
            content.Dock=DockStyle.None;Rail.BringToFront();
        }
        protected override void OnLayout(LayoutEventArgs e) {
            base.OnLayout(e);
            if(Content==null || viewport==null || Rail==null)return;
            int rail=Math.Max(14,SystemInformation.VerticalScrollBarWidth);
            viewport.SetBounds(0,0,Math.Max(1,ClientSize.Width-rail),ClientSize.Height);
            Content.SetBounds(0,0,viewport.Width+SystemInformation.VerticalScrollBarWidth,ClientSize.Height);
            Rail.SetBounds(Math.Max(0,ClientSize.Width-rail),0,rail,ClientSize.Height);Rail.BringToFront();
        }
        public void RefreshScroll(){if(Rail!=null)Rail.Invalidate();}
        protected override void WndProc(ref Message m) {
            base.WndProc(ref m);
            // WM_PRINT does not honor the native child's clipped non-client region.
            if(m.Msg==0x0317 && Rail!=null && Rail.Width>0 && Rail.Height>0)
            using(var bitmap=new Bitmap(Rail.Width,Rail.Height))using(var g=Graphics.FromHdc(m.WParam)){
                Rail.DrawToBitmap(bitmap,Rail.ClientRectangle);g.DrawImageUnscaled(bitmap,Rail.Left,Rail.Top);
            }
        }
    }
    public sealed class ListHost : ScrollHost {
        public DataList List {get{return (DataList)Content;}}
        public ListHost():base(new DataList()){}
    }
    public sealed class LogHost : ScrollHost {
        public LogBox Log {get{return (LogBox)Content;}}
        public LogHost():base(new LogBox()){}
    }
    public sealed class LogBox : TextBox {
        protected override void WndProc(ref Message m){base.WndProc(ref m);if(Parent!=null && Parent.Parent is ScrollHost)((ScrollHost)Parent.Parent).RefreshScroll();}
    }
    public sealed class ScrollRail : Control
    {
        private readonly Control target;
        private bool dragging;
        private int offset;
        [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]
        private struct ScrollInfo {public int Size,Mask,Min,Max,Page,Pos,Track;}
        [System.Runtime.InteropServices.DllImport("user32.dll")]private static extern bool GetScrollInfo(IntPtr h,int bar,ref ScrollInfo info);
        [System.Runtime.InteropServices.DllImport("user32.dll")]private static extern IntPtr SendMessage(IntPtr h,int msg,IntPtr w,IntPtr l);
        public ScrollRail(Control value){target=value;DoubleBuffered=true;TabStop=false;BackColor=Palette.Surface;AccessibleRole=AccessibleRole.ScrollBar;AccessibleName="垂直滚动";Cursor=Cursors.Default;}
        private ScrollInfo Read(){var i=new ScrollInfo();i.Size=System.Runtime.InteropServices.Marshal.SizeOf(i);i.Mask=0x17;if(target.IsHandleCreated)GetScrollInfo(target.Handle,1,ref i);return i;}
        public int Position {get{return Read().Pos;}}
        public int Maximum {get{var i=Read();return Math.Max(i.Min,i.Max-i.Page+1);}}
        public int TrackTop {get{return target is ListView?target.Font.Height+8:0;}}
        public Rectangle ThumbBounds {get{
            var i=Read();int length=Math.Max(1,Height-TrackTop-8),range=i.Max-i.Min+1;
            if(range<=i.Page || range<=0)return Rectangle.Empty;
            int size=Math.Min(length,Math.Max(28,(int)((double)length*i.Page/range)));
            int y=TrackTop+4+(int)((double)(length-size)*(i.Pos-i.Min)/Math.Max(1,Maximum-i.Min));
            return new Rectangle(Math.Max(4,Width/3),y,Math.Max(4,Width/3),size);
        }}
        public void ScrollTo(int value){
            if(!target.IsHandleCreated)return;int desired=Math.Max(0,Math.Min(Maximum,value));
            var list=target as ListView;
            if(list!=null){if(list.Items.Count>0){int row=list.Items[0].Bounds.Height;SendMessage(target.Handle,0x1014,IntPtr.Zero,new IntPtr((desired-Position)*row));}}
            else SendMessage(target.Handle,0x115,new IntPtr(4|(desired<<16)),IntPtr.Zero);
            Invalidate();
        }
        protected override void OnPaint(PaintEventArgs e){
            e.Graphics.Clear(BackColor);if(target is ListView)using(var b=new SolidBrush(Palette.Raised))e.Graphics.FillRectangle(b,0,0,Width,TrackTop);
            var r=ThumbBounds;if(r.IsEmpty)return;e.Graphics.SmoothingMode=SmoothingMode.AntiAlias;
            using(var path=Palette.Round(r,4))using(var b=new SolidBrush(dragging?Palette.Accent:ColorTranslator.FromHtml("#707D90")))e.Graphics.FillPath(b,path);
        }
        protected override void OnMouseDown(MouseEventArgs e){
            base.OnMouseDown(e);if(e.Button!=MouseButtons.Left)return;var r=ThumbBounds;if(r.IsEmpty)return;
            target.Focus();if(r.Contains(e.Location)){dragging=true;offset=e.Y-r.Y;Capture=true;Invalidate();}
            else ScrollTo(Position+(e.Y<r.Y?-1:1)*Math.Max(1,Read().Page));
        }
        protected override void OnMouseMove(MouseEventArgs e){base.OnMouseMove(e);if(dragging){var r=ThumbBounds;int span=Math.Max(1,Height-TrackTop-8-r.Height);ScrollTo((int)Math.Round((double)(e.Y-offset-TrackTop-4)*Maximum/span));}}
        protected override void OnMouseUp(MouseEventArgs e){base.OnMouseUp(e);dragging=false;Capture=false;Invalidate();}
        protected override void OnMouseCaptureChanged(EventArgs e){base.OnMouseCaptureChanged(e);if(!Capture){dragging=false;Invalidate();}}
        protected override void OnMouseWheel(MouseEventArgs e){base.OnMouseWheel(e);ScrollTo(Position-Math.Sign(e.Delta)*Math.Max(1,SystemInformation.MouseWheelScrollLines));}
    }
    public sealed class MenuColors : ProfessionalColorTable
    {
        public override Color ToolStripDropDownBackground {get{return Palette.Surface;}}
        public override Color MenuItemSelected {get{return Palette.Raised;}}
        public override Color MenuItemBorder {get{return Palette.Border;}}
        public override Color MenuBorder {get{return Palette.Border;}}
        public override Color SeparatorDark {get{return Palette.Border;}}
        public override Color SeparatorLight {get{return Palette.Border;}}
    }
    public sealed class MenuRenderer : ToolStripProfessionalRenderer
    {
        public MenuRenderer():base(new MenuColors()){RoundedEdges=false;}
        protected override void OnRenderItemText(ToolStripItemTextRenderEventArgs e){e.TextColor=e.Item.Enabled?Palette.Text:Palette.Muted;base.OnRenderItemText(e);}
    }
}
