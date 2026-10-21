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
                runOnUiThread(()->{try{if(((JSONObject)status).getBoolean("exists"))loadCatalog();else welcome();}catch(Exception e){error(e);}});
            } catch(Exception e) { runOnUiThread(()->error(e)); }
        });
    }
    private Object call(String action,JSONObject request) throws Exception {
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
                if(problem!=null){error(problem);return;}
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
        button("إنشاء متجر جديد",()->request("initialize",obj("branch",branch.getText().toString(),"currency",currency.getText().toString()),r->loadCatalog()));
        button("استيراد قاعدة abud.sQllite موجودة",this::chooseImport);
        text("الإنشاء الجديد يجهز دليل الحسابات والصندوق والبنك والسنة الحالية؛ المنتجات والأرصدة والحركات تبدأ فارغة.");
    }
    private void loadCatalog(){request("schema",new JSONObject(),r->{catalog=(JSONObject)r;tables.clear();JSONArray all=catalog.getJSONArray("tables");for(int i=0;i<all.length();i++){JSONObject t=all.getJSONObject(i);tables.put(t.getString("name"),t);}home();});}
    private String label(String name){return tables.containsKey(name)?tables.get(name).optString("label",name):name;}
    private void home() throws Exception {
        screen("محاسبة المتجر");text("تعمل محلياً • العملة: "+catalog.getString("currency"));
        button("بيع جديد",()->list("SalesInvoice",new JSONObject(),0,""));
        button("شراء جديد واستلام المخزون",()->list("PurchaseInvoice",new JSONObject(),0,""));
        button("التقارير والأرصدة",this::reports);
        button("قيد يومية يدوي / تمويل رأس المال",this::manual);
        JSONObject groups=catalog.getJSONObject("groups");Iterator<String> names=groups.keys();
        while(names.hasNext()){String name=names.next();button(name,()->group(name));}
        button("نسخ احتياطي واستيراد وفحص",this::maintenance);
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
        if(meta.getBoolean("editable"))button("إضافة سجل",()->form(table,null,filters));
        if(table.equals("ManualJournal"))button("قيد يدوي جديد",this::manual);
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
                button("تعديل",()->form(table,row,new JSONObject()));
                button("حذف المسودة / السجل غير المستخدم",()->confirm("الحذف يرفض السجل المستخدم أو المعتمد. هل تريد المتابعة؟",()->request("delete",obj("table",table,"key",k),r->list(table,new JSONObject(),0,""))));
            }
            if(meta.getBoolean("postable")&&!posted)button("اعتماد وترحيل المستند",()->confirm("سيرحّل المستند والمخزون والقيود المرتبطة به، ثم يقفل التعديل. تأكد من اكتمال الأسطر أولاً.",()->request("post",obj("table",table,"id",k.get(k.keys().next())),r->{alert(((JSONObject)r).getString("message"));detail(table,k);})));
            if(meta.getBoolean("freezable")&&!posted)button("تثبيت لقطة الجرد",()->request("freeze",obj("id",k.get("InventoryCountID")),r->detail(table,k)));
            if(table.equals("JournalEntry")&&row.optString("SourceType").equals("ManualJournal"))button("إنشاء قيد عكسي موثق",()->reverse(row.getLong("JournalEntryID")));
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
        for(int i=0;i<kinds.length;i++){String kind=kinds[i],name=names[i];button(name,()->request("report",obj("kind",kind,"from",start.getText().toString(),"to",end.getText().toString()),answer->{
            JSONObject report=(JSONObject)answer;screen(name);if(report.has("asOf"))text(report.getString("asOf"));JSONArray rows=report.getJSONArray("rows");JSONObject scales=report.getJSONObject("scales");StringBuilder csv=new StringBuilder("\uFEFF");
            List<String> headers=new ArrayList<>();if(rows.length()>0){Iterator<String> ks=rows.getJSONObject(0).keys();while(ks.hasNext())headers.add(ks.next());}
            csv.append(csvLine(headers));for(int index=0;index<rows.length();index++){JSONObject row=rows.getJSONObject(index);StringBuilder display=new StringBuilder();List<String> cells=new ArrayList<>();for(String h:headers){String value=row.isNull(h)?"":row.get(h).toString();if(scales.has(h))value=new BigDecimal(value).divide(BigDecimal.valueOf(scales.getInt(h))).toPlainString();cells.add(value);display.append(h).append(": ").append(value).append("\n");}text(display.toString());csv.append(csvLine(cells));}
            if(rows.length()==0)text("لا توجد بيانات خلال الفترة.");else button("حفظ تقرير CSV",()->{csvText=csv.toString();createDocument("text/csv","report-"+LocalDate.now()+".csv",CSV);});
        }));}
        button("دفتر اليومية الكامل",()->list("JournalEntry",new JSONObject(),0,""));button("تفاصيل الحركات المالية",()->list("FinancialTransaction",new JSONObject(),0,""));
    }
    private String csvLine(List<String> cells){List<String> safe=new ArrayList<>();for(String cell:cells){if(!cell.isEmpty()&&"=+-@\t\r\n".indexOf(cell.charAt(0))>=0)cell="'"+cell;safe.add("\""+cell.replace("\"","\"\"")+"\"");}return String.join(",",safe)+"\r\n";}
    private void maintenance()throws Exception {
        screen("حفظ البيانات واستيرادها");text("النسخة الاحتياطية تشمل جميع الجداول والحقول والحركات. احفظ نسخة خارج الهاتف بانتظام.");
        button("تصدير نسخة SQLite كاملة",()->createDocument("application/octet-stream","supermarket-"+LocalDate.now()+".sqlite",BACKUP));
        button("استيراد قاعدة SQLite",this::chooseImport);
        button("فحص سلامة القاعدة والحسابات",()->request("check",new JSONObject(),r->alert(((JSONObject)r).getString("message"))));
        button("تصدير النسخة المحفوظة قبل آخر استيراد",()->{File f=new File(getFilesDir(),"before-restore.sqlite");if(!f.exists())throw new Exception("لا توجد نسخة سابقة للاستيراد.");createDocument("application/octet-stream","before-restore.sqlite",44);});
        text("النسخة المحلية مخصصة لمالك الهاتف. جداول المستخدمين والأدوار محفوظة ضمن قاعدة البيانات.");
    }
    private void createDocument(String mime,String name,int code){Intent i=new Intent(Intent.ACTION_CREATE_DOCUMENT);i.setType(mime);i.addCategory(Intent.CATEGORY_OPENABLE);i.putExtra(Intent.EXTRA_TITLE,name);startActivityForResult(i,code);}
    private void chooseImport(){confirm("سيستبدل الملف قاعدة المتجر الحالية بعد فحصه. تحفظ نسخة من القاعدة السابقة على الهاتف. اختر ملفاً مطابقاً لقاعدة abud.sQllite.",()->{Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT);i.addCategory(Intent.CATEGORY_OPENABLE);i.setType("*/*");startActivityForResult(i,IMPORT);});}
    @Override protected void onActivityResult(int code,int result,Intent data){
        super.onActivityResult(code,result,data);if(result!=RESULT_OK||data==null||data.getData()==null)return;Uri uri=data.getData();pending=true;busy.setText("جارٍ معالجة الملف…");
        worker.execute(()->{Exception problem=null;try{
            if(code==IMPORT){File staged=new File(getFilesDir(),"import.sqlite");try(InputStream in=getContentResolver().openInputStream(uri);OutputStream out=new FileOutputStream(staged)){transfer(in,out,100*1024*1024);}try{call("restore",new JSONObject());}finally{staged.delete();}}
            else if(code==CSV){try(OutputStream out=getContentResolver().openOutputStream(uri,"wt")){out.write(csvText.getBytes(java.nio.charset.StandardCharsets.UTF_8));}}
            else{String file=code==44?new File(getFilesDir(),"before-restore.sqlite").getAbsolutePath():((JSONObject)call("backup",new JSONObject())).getString("file");try(InputStream in=new FileInputStream(file);OutputStream out=getContentResolver().openOutputStream(uri,"wt")){transfer(in,out,Long.MAX_VALUE);}}
        }catch(Exception e){problem=e;}Exception failure=problem;runOnUiThread(()->{pending=false;busy.setText("");if(failure!=null)error(failure);else if(code==IMPORT)loadCatalog();else alert("تم حفظ الملف في المكان الذي اخترته.");});});
    }
    private void transfer(InputStream in,OutputStream out,long max)throws IOException {if(in==null||out==null)throw new IOException("تعذر فتح الملف.");byte[] buffer=new byte[65536];long total=0;int count;while((count=in.read(buffer))!=-1){total+=count;if(total>max)throw new IOException("حجم الملف يتجاوز 100 ميغابايت.");out.write(buffer,0,count);}out.flush();}
    @Override public void onBackPressed(){if(pending){Toast.makeText(this,"انتظر اكتمال الحفظ.",Toast.LENGTH_SHORT).show();return;}if(catalog!=null)act(this::home);else super.onBackPressed();}
    @Override protected void onDestroy(){worker.shutdown();super.onDestroy();}
}
