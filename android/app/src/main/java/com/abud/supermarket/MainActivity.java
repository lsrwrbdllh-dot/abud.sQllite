package com.abud.supermarket;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.DatePickerDialog;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.widget.*;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import org.json.*;
import java.io.*;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.*;
import java.util.concurrent.*;

/** Native Android forms; all accounting writes go to the embedded original engine. */
public final class MainActivity extends Activity {
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private final Map<String,JSONObject> tables=new LinkedHashMap<>();
    private JSONObject catalog;
    private LinearLayout body;
    private TextView title, busy;
    private String database;
    private int generation;
    private boolean pending;
    private static final int IMPORT=41, BACKUP=42, CSV=43;
    private String csvText="";
    private volatile String session="";
    private String exportAction="";
    private JSONObject exportRequest;
    private final int teal=Color.rgb(18,92,96), ink=Color.rgb(23,60,64);
    private interface Reply { void done(Object result) throws Exception; }
    private interface Job { void run() throws Exception; }
    private interface Value { Object read() throws Exception; }

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        database=new File(getFilesDir(),"supermarket.sqlite").getAbsolutePath();
        screen("محاسبة المتجر");
        text("جارٍ فتح قاعدة الهاتف…");
        worker.execute(()->{
            try {
                if(!Python.isStarted()) Python.start(new AndroidPlatform(this));
                Object status=call("status",new JSONObject());
                runOnUiThread(()->{try{route((JSONObject)status);}catch(Exception e){error(e);}});
            } catch(Exception e) { runOnUiThread(()->error(e)); }
        });
    }
    private Object call(String action,JSONObject request) throws Exception {
        request.put("_session",session);
        String json=Python.getInstance().getModule("database.mobile_bridge").callAttr("invoke",database,action,request.toString()).toString();
        JSONObject response=new JSONObject(json);
        if(!response.getBoolean("ok")) throw new Exception(response.getString("error"));
        return response.get("data");
    }
    private void request(String action,JSONObject data,Reply reply) {
        if(pending) {Toast.makeText(this,"انتظر اكتمال العملية الحالية.",Toast.LENGTH_SHORT).show();return;}
        int page=generation;
        pending=true;busy.setText("جارٍ التنفيذ…");
        worker.execute(()->{
            Object result=null;Exception failure=null;
            try {result=call(action,data);}catch(Exception e){failure=e;}
            Object answer=result;Exception problem=failure;
            runOnUiThread(()->{
                pending=false;busy.setText("");
                if(isDestroyed()||isFinishing())return;
                if(problem!=null){if(problem.getMessage()!=null&&(problem.getMessage().contains("انتهت الجلسة")||problem.getMessage().contains("الحساب موقوف"))){clearSession();login(false);}error(problem);return;}
                if(page!=generation)return;
                try{reply.done(answer);}catch(Exception e){error(e);}
            });
        });
    }
    private void act(Job job) { try{job.run();}catch(Exception e){error(e);} }
    private JSONObject obj(Object... pairs) throws JSONException {
        JSONObject result=new JSONObject();for(int i=0;i<pairs.length;i+=2)result.put((String)pairs[i],pairs[i+1]);return result;
    }
    private void screen(String name) {
        generation++;
        LinearLayout root=new LinearLayout(this);root.setOrientation(1);root.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        root.setBackgroundColor(Color.rgb(243,246,246));root.setPadding(16,16,16,16);
        root.setOnApplyWindowInsetsListener((v,insets)->{root.setPadding(16,16+insets.getSystemWindowInsetTop(),16,16+insets.getSystemWindowInsetBottom());return insets;});
        title=new TextView(this);title.setText(name);title.setTextSize(24);title.setTextColor(ink);title.setPadding(0,8,0,12);root.addView(title);
        busy=new TextView(this);busy.setTextColor(teal);root.addView(busy);
        ScrollView scroll=new ScrollView(this);body=new LinearLayout(this);body.setOrientation(1);body.setPadding(0,0,0,32);scroll.addView(body);
        root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));setContentView(root);
        if(catalog!=null)button("الرئيسية",this::home);
    }
    private TextView text(String value) {
        TextView view=new TextView(this);view.setText(value);view.setTextSize(17);view.setTextColor(ink);view.setPadding(4,10,4,10);body.addView(view);return view;
    }
    private Button button(String name,Job job) {
        Button b=new Button(this);b.setText(name);b.setAllCaps(false);b.setTextSize(16);b.setTextColor(Color.WHITE);b.setBackgroundTintList(android.content.res.ColorStateList.valueOf(teal));
        b.setOnClickListener(v->act(()->{if(pending)throw new Exception("انتظر اكتمال العملية الحالية.");job.run();}));body.addView(b);return b;
    }
    private EditText input(String label,String value,int type) {
        text(label);EditText e=new EditText(this);e.setContentDescription(label);e.setText(value);e.setTextSize(17);e.setInputType(type);e.setSingleLine(type!=InputType.TYPE_CLASS_TEXT);body.addView(e);return e;
    }
    private void alert(String message){new AlertDialog.Builder(this).setMessage(message).setPositiveButton("حسناً",null).show();}
    private void error(Exception e){if(!isFinishing())new AlertDialog.Builder(this).setTitle("تعذر تنفيذ العملية").setMessage(e.getMessage()).setPositiveButton("حسناً",null).show();}
    private void confirm(String message,Job action){new AlertDialog.Builder(this).setMessage(message).setNegativeButton("إلغاء",null).setPositiveButton("متابعة",(d,w)->act(action)).show();}
    private void welcome() {
        screen("محاسبة على هاتفك");text("قاعدة SQLite كاملة على الجهاز. لا تحتاج عنوان خادم أو اشتراك استضافة.");
        EditText branch=input("اسم المتجر","",InputType.TYPE_CLASS_TEXT);
        EditText currency=input("اسم العملة","",InputType.TYPE_CLASS_TEXT);
        EditText username=input("اسم مستخدم المدير","",InputType.TYPE_CLASS_TEXT);
        EditText password=input("كلمة مرور المدير (8 أحرف على الأقل)","",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
        button("إنشاء متجر جديد",()->request("initialize",obj("branch",branch.getText().toString(),"currency",currency.getText().toString(),"username",username.getText().toString(),"password",password.getText().toString()),r->{session=((JSONObject)r).getString("token");loadCatalog();}));
        button("استيراد قاعدة abud.sQllite موجودة",this::chooseImport);
        text("الإنشاء الجديد يجهز دليل الحسابات والصندوق والبنك والسنة الحالية؛ المنتجات والأرصدة والحركات تبدأ فارغة.");
    }
    private void clearSession(){session="";catalog=null;tables.clear();csvText="";exportRequest=null;}
    private void route(JSONObject status)throws Exception {if(!status.getBoolean("exists"))welcome();else login(!status.getBoolean("configured"));}
    private void login(boolean setup){
        screen(setup?"إعداد حساب المدير":"تسجيل الدخول");
        text(setup?"أنشئ حساب المدير لحماية بيانات المتجر الحالية. لن تتغير الحركات المحاسبية.":"أدخل حسابك. الصلاحيات والصندوق تحدد ما يمكنك عرضه وتنفيذه.");
        EditText username=input("اسم المستخدم","",InputType.TYPE_CLASS_TEXT);
        EditText password=input("كلمة المرور","",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
        button(setup?"حفظ حساب المدير":"دخول",()->request(setup?"bootstrap":"login",obj("username",username.getText().toString(),"password",password.getText().toString()),r->{session=((JSONObject)r).getString("token");password.setText("");loadCatalog();}));
    }
    private boolean has(String permission){if(catalog==null)return false;JSONObject user=catalog.optJSONObject("user");if(user==null)return false;if(user.optBoolean("manager"))return true;JSONArray rights=user.optJSONArray("permissions");if(rights!=null)for(int i=0;i<rights.length();i++)if(permission.equals(rights.optString(i)))return true;return false;}
    private boolean right(JSONObject meta,String action){return meta.optJSONObject("rights")!=null&&meta.optJSONObject("rights").optBoolean(action);}
    private void password(){
        screen("تغيير كلمة المرور");
        EditText old=input("كلمة المرور الحالية","",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
        EditText next=input("كلمة المرور الجديدة","",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
        EditText repeat=input("تأكيد كلمة المرور الجديدة","",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
        button("حفظ كلمة المرور",()->{if(!next.getText().toString().equals(repeat.getText().toString()))throw new Exception("تأكيد كلمة المرور غير مطابق.");request("password",obj("old",old.getText().toString(),"password",next.getText().toString()),r->{clearSession();login(false);});});
    }
    private void users(){
        screen("إدارة الموظفين والصلاحيات");
        request("users",new JSONObject(),r->{JSONObject data=(JSONObject)r;
            button("إضافة موظف",()->userForm(data,null));JSONArray users=data.getJSONArray("users");
            for(int i=0;i<users.length();i++){JSONObject user=users.getJSONObject(i);button(user.getString("Username")+" — "+user.getString("EmployeeName")+(user.optInt("IsActive")==1?" — نشط":" — موقوف"),()->userForm(data,user));}
            text("لكل موظف حسابه. تعديل الحساب أو الصلاحيات ينهي جلساته. لا يمكن إيقاف آخر مدير نشط.");
        });
    }
    private void userForm(JSONObject data,JSONObject user)throws Exception {
        screen(user==null?"إضافة موظف":"تعديل حساب الموظف");
        EditText name=input("اسم الموظف",user==null?"":user.getString("EmployeeName"),InputType.TYPE_CLASS_TEXT);
        EditText username=input("اسم مستخدم الموظف",user==null?"":user.getString("Username"),InputType.TYPE_CLASS_TEXT);
        EditText password=input("كلمة مرور الموظف (اتركها فارغة للإبقاء على الحالية)","",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
        CheckBox active=new CheckBox(this);active.setText("الحساب نشط");active.setChecked(user==null||user.optInt("IsActive")==1);body.addView(active);
        List<String> codes=Arrays.asList("cashier","purchasing","stock","accountant","manager");
        List<String> labels=new ArrayList<>();for(String code:codes)labels.add(data.getJSONObject("roles").getString(code));
        text("دور الموظف");Spinner role=new Spinner(this);role.setContentDescription("دور الموظف");role.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,labels));body.addView(role);
        String initial=user==null?"cashier":user.getJSONArray("roles").optString(0,"cashier");role.setSelection(Math.max(0,codes.indexOf(initial)));
        JSONObject overrides=user==null?new JSONObject():new JSONObject(user.getJSONObject("overrides").toString());
        final String[] chosen={initial};
        role.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){public void onNothingSelected(AdapterView<?> p){}public void onItemSelected(AdapterView<?> p,View v,int pos,long id){String next=codes.get(pos);if(!next.equals(chosen[0])){Iterator<String> ks=overrides.keys();while(ks.hasNext()){ks.next();ks.remove();}chosen[0]=next;}}});
        button("تخصيص صلاحيات الموظف",()->{
            String code=codes.get(role.getSelectedItemPosition());
            if(code.equals("manager")){alert("المدير يملك جميع الصلاحيات، مع بقاء ضوابط الحركات المعتمدة.");return;}
            JSONObject catalog=data.getJSONObject("permissions");List<String> keys=new ArrayList<>();Iterator<String> iterator=catalog.keys();while(iterator.hasNext())keys.add(iterator.next());Collections.sort(keys);
            Set<String> defaults=new HashSet<>();JSONArray rights=data.getJSONObject("defaults").getJSONArray(code);for(int i=0;i<rights.length();i++)defaults.add(rights.getString(i));
            String[] names=new String[keys.size()];boolean[] checked=new boolean[keys.size()];for(int i=0;i<keys.size();i++){String k=keys.get(i);names[i]=catalog.getString(k);checked[i]=overrides.has(k)?overrides.getBoolean(k):defaults.contains(k);}
            new AlertDialog.Builder(this).setTitle("صلاحيات — "+data.getJSONObject("roles").getString(code)).setMultiChoiceItems(names,checked,(d,index,value)->checked[index]=value).setNegativeButton("إلغاء",null).setPositiveButton("تطبيق",(d,w)->act(()->{
                Iterator<String> ks=overrides.keys();while(ks.hasNext()){ks.next();ks.remove();}
                for(int i=0;i<keys.size();i++)if(checked[i]!=defaults.contains(keys.get(i)))overrides.put(keys.get(i),checked[i]);
            })).show();
        });
        text("الصناديق والبنوك المسموح استخدامها (إذن جميع الصناديق يتجاوز هذه القائمة)");
        Map<Integer,CheckBox> accounts=new LinkedHashMap<>();Set<Integer> selected=new HashSet<>();if(user!=null){JSONArray all=user.getJSONArray("cash");for(int i=0;i<all.length();i++)selected.add(all.getInt(i));}
        JSONArray all=data.getJSONArray("accounts");for(int i=0;i<all.length();i++){JSONObject account=all.getJSONObject(i);int id=account.getInt("FinancialAccountID");CheckBox checkbox=new CheckBox(this);checkbox.setText(account.getString("AccountName"));checkbox.setChecked(selected.contains(id));body.addView(checkbox);accounts.put(id,checkbox);}
        button("حفظ الموظف والصلاحيات",()->{
            JSONArray cash=new JSONArray();for(Map.Entry<Integer,CheckBox> entry:accounts.entrySet())if(entry.getValue().isChecked())cash.put(entry.getKey());
            JSONObject req=obj("name",name.getText().toString(),"username",username.getText().toString(),"password",password.getText().toString(),"active",active.isChecked(),"role",codes.get(role.getSelectedItemPosition()),"overrides",overrides,"cash",cash);
            if(user!=null)req.put("id",user.getInt("UserID"));request("user_save",req,r->{password.setText("");if(user!=null&&user.getInt("UserID")==catalog.getJSONObject("user").getInt("id")){clearSession();login(false);}else users();});
        });
        text("عرض عمليات الجميع يمنح الوصول إلى مستندات الموظفين الآخرين ضمن الأقسام المسموحة. النسخ الاحتياطي الكامل يحتوي جميع بيانات المتجر وحسابات المستخدمين.");
    }
    private void loadCatalog(){request("schema",new JSONObject(),r->{catalog=(JSONObject)r;tables.clear();JSONArray all=catalog.getJSONArray("tables");for(int i=0;i<all.length();i++){JSONObject t=all.getJSONObject(i);tables.put(t.getString("name"),t);}home();});}
    private String label(String name){return tables.containsKey(name)?tables.get(name).optString("label",name):name;}
    private void home() throws Exception {
        screen("محاسبة المتجر");text("تعمل محلياً • العملة: "+catalog.getString("currency"));
        text("المستخدم: "+catalog.getJSONObject("user").getString("username"));
        if(tables.containsKey("SalesInvoice"))button("بيع جديد",()->list("SalesInvoice",new JSONObject(),0,""));
        if(tables.containsKey("PurchaseInvoice"))button("شراء جديد واستلام المخزون",()->list("PurchaseInvoice",new JSONObject(),0,""));
        button("التقارير والأرصدة",this::reports);
        if(has("journal.manual"))button("قيد يومية يدوي / تمويل رأس المال",this::manual);
        if(has("users.manage"))button("إدارة الموظفين والصلاحيات",this::users);
        JSONObject groups=catalog.getJSONObject("groups");Iterator<String> names=groups.keys();
        while(names.hasNext()){String name=names.next();button(name,()->group(name));}
        if(has("backup.create")||has("backup.restore")||has("database.check"))button("نسخ احتياطي واستيراد وفحص",this::maintenance);
        button("تغيير كلمة المرور",this::password);
        button("تسجيل الخروج",()->request("logout",new JSONObject(),r->{clearSession();login(false);}));
        text("ابدأ بالمنتجات والموردين. اعتماد الشراء يثبت الاستحقاق؛ المخزون يدخل عند اعتماد الاستلام ودفعاته. المستند المعتمد لا يعدل مباشرة.");
    }
    private void group(String name) throws Exception {
        screen(name);JSONArray members=catalog.getJSONObject("groups").getJSONArray(name);
        for(int i=0;i<members.length();i++){String t=members.getString(i);button(label(t),()->list(t,new JSONObject(),0,""));}
    }
    private String show(JSONObject c,Object value) {
        if(value==null||value==JSONObject.NULL)return "—";
        if(c.optBoolean("secret"))return "••••••••";
        if(c.optInt("scale",1)>1)return new BigDecimal(value.toString()).divide(BigDecimal.valueOf(c.optInt("scale"))).toPlainString();
        if(c.optBoolean("boolean"))return value.toString().equals("1")?"نعم":"لا";
        return catalog.optJSONObject("choices").optString(value.toString(),value.toString());
    }
    private JSONObject key(String table,JSONObject row)throws Exception {
        JSONObject k=new JSONObject();JSONArray fields=tables.get(table).getJSONArray("columns");for(int i=0;i<fields.length();i++){JSONObject f=fields.getJSONObject(i);if(f.getInt("pk")>0)k.put(f.getString("name"),row.get(f.getString("name")));}return k;
    }
    private String summary(String table,JSONObject row) throws Exception {
        StringBuilder s=new StringBuilder();JSONArray fields=tables.get(table).getJSONArray("columns");
        for(int i=0;i<fields.length();i++){JSONObject f=fields.getJSONObject(i);String n=f.getString("name");if(f.optBoolean("secret"))continue;
            Object v=row.opt(n);if(v==null||v==JSONObject.NULL)continue;
            if(s.length()>0)s.append(" · ");s.append(f.getString("label")).append(": ").append(show(f,v));if(s.length()>200)break;}
        return s.toString();
    }
    private void list(String table,JSONObject filters,int offset,String search)throws Exception {
        screen(label(table));JSONObject meta=tables.get(table);
        if(filters.length()>0)text("سجلات مرتبطة بالمستند المحدد");
        EditText query=input("بحث داخل السجلات",search,InputType.TYPE_CLASS_TEXT);
        button("بحث",()->list(table,filters,0,query.getText().toString()));
        if(meta.getBoolean("editable")&&right(meta,"create"))button("إضافة سجل",()->form(table,null,filters));
        if(table.equals("ManualJournal")&&has("journal.manual"))button("قيد يدوي جديد",this::manual);
        if(right(meta,"export"))button("تصدير السجلات CSV",()->prepareExport("export_rows",obj("table",table,"filters",filters,"search",search)));
        request("rows",obj("table",table,"filters",filters,"offset",offset,"search",search),answer->{
            JSONObject result=(JSONObject)answer;JSONArray rows=result.getJSONArray("rows");
            text("إجمالي السجلات: "+result.getInt("total")+" • الصفحة "+(offset/50+1));
            for(int i=0;i<rows.length();i++){JSONObject row=rows.getJSONObject(i);button(summary(table,row),()->detail(table,key(table,row)));}
            if(offset>0)button("الصفحة السابقة",()->list(table,filters,Math.max(0,offset-50),search));
            if(offset+50<result.getInt("total"))button("الصفحة التالية",()->list(table,filters,offset+50,search));
            if(rows.length()==0)text("لا توجد سجلات؛ يمكنك إضافة البيانات أو تغيير البحث.");
        });
    }
    private void detail(String table,JSONObject k)throws Exception {
        screen(label(table));request("record",obj("table",table,"key",k),answer->{
            JSONObject row=(JSONObject)answer,meta=tables.get(table);JSONArray fields=meta.getJSONArray("columns");
            for(int i=0;i<fields.length();i++){JSONObject f=fields.getJSONObject(i);text(f.getString("label")+": "+show(f,row.opt(f.getString("name"))));}
            if(row.has("_summary")){JSONObject summary=row.getJSONObject("_summary");Iterator<String> names=summary.keys();while(names.hasNext()){String name=names.next();text(name+": "+summary.getString(name));}}
            boolean posted=row.optString("Status").equals("POSTED");
            if(meta.getBoolean("editable")&&!posted){
                if(right(meta,"update"))button("تعديل",()->form(table,row,new JSONObject()));
                if(right(meta,"delete"))button("حذف المسودة / السجل غير المستخدم",()->confirm("الحذف يرفض السجل المستخدم أو المعتمد. هل تريد المتابعة؟",()->request("delete",obj("table",table,"key",k),r->list(table,new JSONObject(),0,""))));
            }
            if(right(meta,"print"))button("طباعة المستند",()->print(label(table),"print_record",obj("table",table,"key",k),table));
            if(meta.getBoolean("postable")&&!posted)button("اعتماد وترحيل المستند",()->confirm("سيرحّل المستند والمخزون والقيود المرتبطة به، ثم يقفل التعديل. تأكد من اكتمال الأسطر أولاً.",()->request("post",obj("table",table,"id",k.get(k.keys().next())),r->{alert(((JSONObject)r).getString("message"));detail(table,k);})));
            if(meta.getBoolean("freezable")&&!posted)button("تثبيت لقطة الجرد",()->request("freeze",obj("id",k.get("InventoryCountID")),r->detail(table,k)));
            if(table.equals("JournalEntry")&&row.optString("SourceType").equals("ManualJournal")&&has("journal.reverse"))button("إنشاء قيد عكسي موثق",()->reverse(row.getLong("JournalEntryID")));
            JSONArray children=meta.getJSONArray("children");
            if(children.length()>0)text("الأسطر والسجلات المرتبطة");
            for(int i=0;i<children.length();i++){JSONObject ch=children.getJSONObject(i);String child=ch.getString("table");Object target=row.opt(ch.getString("target"));if(target==null||target==JSONObject.NULL)continue;
                JSONObject filter=obj(ch.getString("field"),target);button(label(child)+" — "+ch.getString("field"),()->list(child,filter,0,""));}
            button("رجوع إلى القائمة",()->list(table,new JSONObject(),0,""));
        });
    }
    private String editable(JSONObject c,Object value){
        if(value==null||value==JSONObject.NULL||c.optBoolean("secret"))return "";
        int scale=c.optInt("scale",1);return scale==1?value.toString():new BigDecimal(value.toString()).divide(BigDecimal.valueOf(scale)).toPlainString();
    }
    private void form(String table,JSONObject row,JSONObject defaults)throws Exception {
        screen((row==null?"إضافة — ":"تعديل — ")+label(table));
        text("المبالغ بالعملة الرئيسية بدقة منزلتين؛ الكميات بدقة ثلاث منازل. الحقول ذات * مطلوبة. الأرقام المرجعية تختار من السجلات.");
        Map<String,Value> values=new LinkedHashMap<>();JSONArray fields=tables.get(table).getJSONArray("columns");
        for(int i=0;i<fields.length();i++){
            JSONObject c=fields.getJSONObject(i);String name=c.getString("name");Object current=row==null?defaults.opt(name):row.opt(name);
            if(c.getBoolean("automatic")||(row!=null&&c.getInt("pk")>0)){if(row!=null)text(c.getString("label")+": "+show(c,current));continue;}
            String fieldTitle=c.getString("label")+(c.getInt("notnull")==1?" *":"");
            if(c.optBoolean("secret"))fieldTitle="كلمة المرور الجديدة (8 أحرف؛ اتركها فارغة للإبقاء على الحالية)";
            final String titleText=fieldTitle;
            if(!c.isNull("foreign")){
                text(fieldTitle);Button pick=new Button(this);body.addView(pick);final Object[] selected={current};
                pick.setText(current==null||current==JSONObject.NULL?"اختر سجلاً":("السجل #"+current));
                pick.setOnClickListener(v->act(()->chooseForeign(c.getString("foreign"),c.optInt("notnull")==0,choice->{selected[0]=choice;pick.setText(choice==null?"بدون ارتباط":"السجل #"+choice);})));values.put(name,()->selected[0]==null?JSONObject.NULL:selected[0].toString());
            }else if(c.optBoolean("boolean")){
                CheckBox b=new CheckBox(this);b.setText(fieldTitle);String fallback=c.optString("dflt_value","0");b.setChecked(current==null?fallback.equals("1"):current.toString().equals("1"));body.addView(b);values.put(name,()->b.isChecked()?"1":"0");
            }else if(c.getJSONArray("choices").length()>0){
                JSONArray options=c.getJSONArray("choices");List<String> labels=new ArrayList<>();int selected=0;
                for(int j=0;j<options.length();j++){String option=options.getString(j);labels.add(catalog.getJSONObject("choices").optString(option,option));if(option.equals(String.valueOf(current)))selected=j;}
                text(fieldTitle);Spinner spin=new Spinner(this);spin.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,labels));spin.setSelection(selected);body.addView(spin);values.put(name,()->options.getString(spin.getSelectedItemPosition()));
            }else{
                int type=c.getString("type").equals("INTEGER")?InputType.TYPE_CLASS_NUMBER|InputType.TYPE_NUMBER_FLAG_DECIMAL|InputType.TYPE_NUMBER_FLAG_SIGNED:InputType.TYPE_CLASS_TEXT;
                if(c.optBoolean("secret"))type=InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD;
                String value=editable(c,current);
                if(value.isEmpty()&&row==null&&!c.optBoolean("secret")){
                    if(name.endsWith("Date"))value=LocalDate.now().toString();
                    else if(name.equals("PayrollMonth"))value=""+LocalDate.now().getMonthValue();
                    else if(name.equals("PayrollYear"))value=""+LocalDate.now().getYear();
                    else if(!c.isNull("dflt_value"))value=c.getString("dflt_value").replace("'","");
                }
                EditText entry=input(fieldTitle,value,type);
                if(name.endsWith("Date"))entry.setOnClickListener(v->{LocalDate d;try{d=LocalDate.parse(entry.getText().toString());}catch(Exception e){d=LocalDate.now();}new DatePickerDialog(this,(view,y,m,day)->entry.setText(LocalDate.of(y,m+1,day).toString()),d.getYear(),d.getMonthValue()-1,d.getDayOfMonth()).show();});
                values.put(name,()->{String text=entry.getText().toString().trim();if(c.optBoolean("secret")&&text.isEmpty())return null;
                    if(text.isEmpty()){if(c.getInt("notnull")==1&&c.isNull("dflt_value"))throw new Exception("أدخل "+titleText);return c.isNull("dflt_value")?JSONObject.NULL:null;}return text;});
            }
        }
        button("حفظ المسودة / البيانات",()->{
            JSONObject data=new JSONObject();for(Map.Entry<String,Value> e:values.entrySet()){Object v=e.getValue().read();if(v!=null)data.put(e.getKey(),v);}
            JSONObject req=obj("table",table,"values",data);if(row!=null)req.put("key",key(table,row));
            request("save",req,r->detail(table,((JSONObject)r).getJSONObject("key")));
        });
        text("الحفظ ينشئ مسودة. افتح تفاصيل المستند لإضافة الأسطر واعتماده. الحقول المحسوبة يحتسبها البرنامج.");
    }
    private void chooseForeign(String table,boolean nullable,Reply result)throws Exception {
        LinearLayout panel=new LinearLayout(this);panel.setOrientation(1);EditText query=new EditText(this);query.setHint("بحث بالاسم أو الرقم");query.setContentDescription("بحث عن سجل مرتبط");panel.addView(query);
        ListView list=new ListView(this);panel.addView(list,new LinearLayout.LayoutParams(-1,600));
        LinearLayout paging=new LinearLayout(this);Button previous=new Button(this),next=new Button(this);previous.setText("السابق");next.setText("التالي");paging.addView(previous);paging.addView(next);panel.addView(paging);
        AlertDialog.Builder builder=new AlertDialog.Builder(this).setTitle("اختيار — "+label(table)).setView(panel).setNegativeButton("إلغاء",null);
        if(nullable)builder.setNeutralButton("بدون ارتباط",(d,w)->act(()->result.done(null)));
        AlertDialog dialog=builder.create();
        List<JSONObject> records=new ArrayList<>();final int[] offset={0};
        Runnable load=()->act(()->request("rows",obj("table",table,"search",query.getText().toString(),"offset",offset[0]),answer->{
            JSONObject response=(JSONObject)answer;JSONArray rows=response.getJSONArray("rows");List<String> labels=new ArrayList<>();records.clear();
            for(int i=0;i<rows.length();i++){JSONObject r=rows.getJSONObject(i);records.add(r);labels.add(summary(table,r));}
            list.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_list_item_1,labels));previous.setEnabled(offset[0]>0);next.setEnabled(offset[0]+50<response.getInt("total"));
        }));
        query.addTextChangedListener(new android.text.TextWatcher(){public void beforeTextChanged(CharSequence s,int st,int count,int after){}public void onTextChanged(CharSequence s,int st,int before,int count){}public void afterTextChanged(android.text.Editable e){offset[0]=0;query.removeCallbacks(load);query.postDelayed(load,450);}});
        previous.setOnClickListener(v->{offset[0]=Math.max(0,offset[0]-50);load.run();});next.setOnClickListener(v->{offset[0]+=50;load.run();});
        list.setOnItemClickListener((parent,v,index,id)->act(()->{JSONObject k=key(table,records.get(index));result.done(k.get(k.keys().next()));dialog.dismiss();}));dialog.show();load.run();
    }
    private EditText dateField(String label,String value){EditText e=input(label,value,InputType.TYPE_CLASS_DATETIME);e.setOnClickListener(v->{LocalDate d=LocalDate.now();new DatePickerDialog(this,(p,y,m,day)->e.setText(LocalDate.of(y,m+1,day).toString()),d.getYear(),d.getMonthValue()-1,d.getDayOfMonth()).show();});return e;}
    private void manual() throws Exception {
        screen("قيد يومية يدوي");text("لتمويل الصندوق: مدين حساب الصندوق ودائن رأس المال. أدخل سطرين أو أكثر؛ يجب تساوي المدين والدائن.");
        EditText day=dateField("تاريخ القيد",LocalDate.now().toString());EditText note=input("وصف القيد","",InputType.TYPE_CLASS_TEXT);
        List<JSONObject> lines=new ArrayList<>();LinearLayout rows=new LinearLayout(this);rows.setOrientation(1);body.addView(rows);
        button("إضافة سطر",()->chooseForeign("ChartOfAccounts",false,account->{
            LinearLayout panel=new LinearLayout(this);panel.setOrientation(1);EditText debit=new EditText(this),credit=new EditText(this);debit.setHint("مدين");credit.setHint("دائن");debit.setText("0");credit.setText("0");
            debit.setContentDescription("مبلغ مدين");credit.setContentDescription("مبلغ دائن");
            debit.setInputType(InputType.TYPE_CLASS_NUMBER|InputType.TYPE_NUMBER_FLAG_DECIMAL);credit.setInputType(InputType.TYPE_CLASS_NUMBER|InputType.TYPE_NUMBER_FLAG_DECIMAL);panel.addView(debit);panel.addView(credit);
            new AlertDialog.Builder(this).setTitle("الحساب #"+account).setView(panel).setNegativeButton("إلغاء",null).setPositiveButton("إضافة",(d,w)->act(()->{
                JSONObject line=obj("account",account,"debit",debit.getText().toString(),"credit",credit.getText().toString());lines.add(line);
                Button row=new Button(this);row.setText("الحساب #"+account+" | مدين "+debit.getText()+" | دائن "+credit.getText()+" — حذف");rows.addView(row);row.setOnClickListener(v->{lines.remove(line);rows.removeView(row);});
            })).show();
        }));
        button("اعتماد القيد المتوازن",()->{
            confirm("اعتماد هذا القيد المحاسبي؟",()->{
                request("manual",obj("date",day.getText().toString(),"description",note.getText().toString(),"lines",new JSONArray(lines)),r->{
                    detail("JournalEntry",obj("JournalEntryID",((JSONObject)r).getLong("id")));
                });
            });
        });
    }
    private void reverse(long id) throws Exception {
        screen("عكس قيد يدوي #"+id);EditText day=dateField("تاريخ القيد العكسي",LocalDate.now().toString());EditText why=input("سبب التصحيح","",InputType.TYPE_CLASS_TEXT);
        button("اعتماد القيد العكسي",()->{
            confirm("سينشأ قيد مقابل مرتبط بالأصل. هل تريد المتابعة؟",()->{
                request("reverse",obj("id",id,"date",day.getText().toString(),"description",why.getText().toString()),r->{
                    detail("JournalEntry",obj("JournalEntryID",((JSONObject)r).getLong("id")));
                });
            });
        });
    }
    private void reports() throws Exception {
        screen("التقارير");EditText start=dateField("من",LocalDate.now().withDayOfMonth(1).toString()),end=dateField("إلى",LocalDate.now().toString());
        String[] kinds={"trial","income","financial","stock","transit","customers","suppliers"},names={"ميزان المراجعة","قائمة الدخل","أرصدة وحركات الصناديق والبنوك","المخزون والدفعات والصلاحية الحالية","المخزون قيد النقل","ذمم العملاء والمقدمات","ذمم الموردين والمقدمات"};
        for(int i=0;i<kinds.length;i++){String kind=kinds[i],name=names[i];if(!has("report."+kind+".view"))continue;
            button(name,()->request("report",obj("kind",kind,"from",start.getText().toString(),"to",end.getText().toString()),answer->{
                JSONObject report=(JSONObject)answer;screen(name);if(report.has("asOf"))text(report.getString("asOf"));JSONArray rows=report.getJSONArray("rows");JSONObject scales=report.getJSONObject("scales");
                for(int index=0;index<rows.length();index++){JSONObject row=rows.getJSONObject(index);StringBuilder display=new StringBuilder();Iterator<String> headers=row.keys();while(headers.hasNext()){String h=headers.next();String value=cell(row,h,scales);display.append(h).append(": ").append(value).append("\n");}text(display.toString());}
                if(rows.length()==0)text("لا توجد بيانات خلال الفترة.");
                if(has("report."+kind+".export"))button("حفظ تقرير CSV",()->prepareExport("report",obj("kind",kind,"from",start.getText().toString(),"to",end.getText().toString(),"mode","export")));
                if(has("report."+kind+".print"))button("طباعة التقرير",()->print(name,"report",obj("kind",kind,"from",start.getText().toString(),"to",end.getText().toString(),"mode","print"),null));
            }));
        }
        if(tables.containsKey("JournalEntry"))button("دفتر اليومية الكامل",()->list("JournalEntry",new JSONObject(),0,""));
        if(tables.containsKey("FinancialTransaction"))button("تفاصيل الحركات المالية",()->list("FinancialTransaction",new JSONObject(),0,""));
    }
    private String cell(JSONObject row,String key,JSONObject scales)throws Exception {
        if(row.isNull(key))return "";String value=row.get(key).toString();return scales.has(key)?new BigDecimal(value).divide(BigDecimal.valueOf(scales.getInt(key))).toPlainString():value;
    }
    private String csv(JSONObject response)throws Exception {
        JSONArray rows=response.getJSONArray("rows");JSONObject scales=response.optJSONObject("scales");if(scales==null)scales=new JSONObject();
        List<String> headers=new ArrayList<>();if(rows.length()>0){Iterator<String> ks=rows.getJSONObject(0).keys();while(ks.hasNext())headers.add(ks.next());}
        StringBuilder out=new StringBuilder("\uFEFF");out.append(csvLine(headers));
        for(int i=0;i<rows.length();i++){List<String> cells=new ArrayList<>();for(String h:headers)cells.add(cell(rows.getJSONObject(i),h,scales));out.append(csvLine(cells));}return out.toString();
    }
    private void prepareExport(String action,JSONObject req){request(action,req,r->{exportAction=action;exportRequest=req;createDocument("text/csv","report-"+LocalDate.now()+".csv",CSV);});}
    private void print(String name,String action,JSONObject req,String table){
        android.print.PrintManager manager=(android.print.PrintManager)getSystemService(PRINT_SERVICE);
        manager.print(name,new android.print.PrintDocumentAdapter(){
            public void onLayout(android.print.PrintAttributes old,android.print.PrintAttributes current,android.os.CancellationSignal signal,LayoutResultCallback callback,Bundle extras){if(signal.isCanceled()){callback.onLayoutCancelled();return;}callback.onLayoutFinished(new android.print.PrintDocumentInfo.Builder("document.pdf").setContentType(android.print.PrintDocumentInfo.CONTENT_TYPE_DOCUMENT).build(),true);}
            public void onWrite(android.print.PageRange[] ranges,android.os.ParcelFileDescriptor destination,android.os.CancellationSignal signal,WriteResultCallback callback){worker.execute(()->{
                try(android.graphics.pdf.PdfDocument pdf=new android.graphics.pdf.PdfDocument()){
                    JSONObject data=(JSONObject)call(action,req);List<String> lines=new ArrayList<>();lines.add(name);
                    if(table!=null){printRow(lines,table,data);JSONArray children=data.optJSONArray("_lines");if(children!=null)for(int i=0;i<children.length();i++){JSONObject child=children.getJSONObject(i);lines.add(label(child.getString("table")));JSONArray rows=child.getJSONArray("rows");for(int j=0;j<rows.length();j++){lines.add("────────");printRow(lines,child.getString("table"),rows.getJSONObject(j));}}}
                    else{JSONArray rows=data.getJSONArray("rows");JSONObject scales=data.getJSONObject("scales");for(int i=0;i<rows.length();i++){JSONObject row=rows.getJSONObject(i);Iterator<String> keys=row.keys();while(keys.hasNext()){String k=keys.next();lines.add(k+": "+cell(row,k,scales));}lines.add("────────");}}
                    List<String> wrapped=new ArrayList<>();for(String line:lines){for(int i=0;i<line.length();i+=65)wrapped.add(line.substring(i,Math.min(i+65,line.length())));}
                    android.graphics.Paint paint=new android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG);paint.setTextSize(12);paint.setTextAlign(android.graphics.Paint.Align.RIGHT);
                    for(int offset=0,pageNo=1;offset<wrapped.size();offset+=48,pageNo++){if(signal.isCanceled()){callback.onWriteCancelled();return;}
                        android.graphics.pdf.PdfDocument.Page page=pdf.startPage(new android.graphics.pdf.PdfDocument.PageInfo.Builder(595,842,pageNo).create());int count=Math.min(48,wrapped.size()-offset);for(int i=0;i<count;i++)page.getCanvas().drawText(wrapped.get(offset+i),555,50+i*16,paint);pdf.finishPage(page);}
                    try(OutputStream out=new FileOutputStream(destination.getFileDescriptor())){pdf.writeTo(out);}callback.onWriteFinished(new android.print.PageRange[]{android.print.PageRange.ALL_PAGES});
                }catch(Exception error){callback.onWriteFailed(error.getMessage());}
            });}
        },new android.print.PrintAttributes.Builder().setMediaSize(android.print.PrintAttributes.MediaSize.ISO_A4).build());
    }
    private void printRow(List<String> lines,String table,JSONObject row)throws Exception {
        JSONObject meta=tables.get(table);if(meta==null)return;JSONArray fields=meta.getJSONArray("columns");for(int i=0;i<fields.length();i++){JSONObject field=fields.getJSONObject(i);if(!field.optBoolean("secret"))lines.add(field.getString("label")+": "+show(field,row.opt(field.getString("name"))));}
        JSONObject totals=row.optJSONObject("_summary");if(totals!=null){Iterator<String> keys=totals.keys();while(keys.hasNext()){String key=keys.next();lines.add(key+": "+totals.getString(key));}}
    }
    private String csvLine(List<String> cells){List<String> safe=new ArrayList<>();for(String cell:cells){if(!cell.isEmpty()&&"=+-@\t\r\n".indexOf(cell.charAt(0))>=0)cell="'"+cell;safe.add("\""+cell.replace("\"","\"\"")+"\"");}return String.join(",",safe)+"\r\n";}
    private void maintenance()throws Exception {
        screen("حفظ البيانات واستيرادها");text("النسخة الاحتياطية تشمل جميع الجداول والحقول والحركات. احفظ نسخة خارج الهاتف بانتظام.");
        if(has("backup.create"))button("تصدير نسخة SQLite كاملة",()->createDocument("application/octet-stream","supermarket-"+LocalDate.now()+".sqlite",BACKUP));
        if(has("backup.restore"))button("استيراد قاعدة SQLite",this::chooseImport);
        if(has("database.check"))button("فحص سلامة القاعدة والحسابات",()->request("check",new JSONObject(),r->alert(((JSONObject)r).getString("message"))));
        if(has("backup.create"))button("تصدير النسخة المحفوظة قبل آخر استيراد",()->createDocument("application/octet-stream","before-restore.sqlite",44));
        text("النسخة الكاملة تشمل جميع بيانات المتجر وحسابات الموظفين. الاستيراد ينهي الجلسات ويتطلب الدخول بحساب موجود في القاعدة المستوردة.");
    }
    private void createDocument(String mime,String name,int code){Intent i=new Intent(Intent.ACTION_CREATE_DOCUMENT);i.setType(mime);i.addCategory(Intent.CATEGORY_OPENABLE);i.putExtra(Intent.EXTRA_TITLE,name);startActivityForResult(i,code);}
    private void chooseImport(){confirm("سيستبدل الملف قاعدة المتجر الحالية بعد فحصه. تحفظ نسخة من القاعدة السابقة على الهاتف. اختر ملفاً مطابقاً لقاعدة abud.sQllite.",()->{Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT);i.addCategory(Intent.CATEGORY_OPENABLE);i.setType("*/*");startActivityForResult(i,IMPORT);});}
    @Override protected void onActivityResult(int code,int result,Intent data){
        super.onActivityResult(code,result,data);if(result!=RESULT_OK||data==null||data.getData()==null)return;Uri uri=data.getData();pending=true;busy.setText("جارٍ معالجة الملف…");
        worker.execute(()->{Exception problem=null;try{
            if(code==IMPORT){File staged=new File(getFilesDir(),"import.sqlite");try(InputStream in=getContentResolver().openInputStream(uri);OutputStream out=new FileOutputStream(staged)){transfer(in,out,100*1024*1024);}try{call("restore",new JSONObject());}finally{staged.delete();}}
            else if(code==CSV){if(exportRequest==null)throw new Exception("أعد فتح التقرير لتصديره.");String content=csv((JSONObject)call(exportAction,exportRequest));try(OutputStream out=getContentResolver().openOutputStream(uri,"wt")){out.write(content.getBytes(java.nio.charset.StandardCharsets.UTF_8));}}
            else{String file=((JSONObject)call(code==44?"backup_previous":"backup",new JSONObject())).getString("file");try(InputStream in=new FileInputStream(file);OutputStream out=getContentResolver().openOutputStream(uri,"wt")){transfer(in,out,Long.MAX_VALUE);}}
        }catch(Exception e){problem=e;}Exception failure=problem;runOnUiThread(()->{pending=false;busy.setText("");if(isDestroyed()||isFinishing())return;if(failure!=null)error(failure);else if(code==IMPORT){clearSession();request("status",new JSONObject(),r->route((JSONObject)r));}else alert("تم حفظ الملف في المكان الذي اخترته.");});});
    }
    private void transfer(InputStream in,OutputStream out,long max)throws IOException {if(in==null||out==null)throw new IOException("تعذر فتح الملف.");byte[] buffer=new byte[65536];long total=0;int count;while((count=in.read(buffer))!=-1){total+=count;if(total>max)throw new IOException("حجم الملف يتجاوز 100 ميغابايت.");out.write(buffer,0,count);}out.flush();}
    @Override public void onBackPressed(){if(pending){Toast.makeText(this,"انتظر اكتمال الحفظ.",Toast.LENGTH_SHORT).show();return;}if(catalog!=null)act(this::home);else super.onBackPressed();}
    @Override protected void onDestroy(){worker.shutdown();super.onDestroy();}
}
