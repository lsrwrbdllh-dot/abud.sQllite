# سجل تنفيذ صلاحيات الموظفين — ماذا ولماذا وأين

تاريخ التفويض: 2026-10-26. المتطلبات المعتمدة: الأدوار الخمسة، تخصيص صلاحيات كل موظف، النطاق والصناديق، الأذونات الحساسة، والتدقيق. طلب المالك حفظ الكود وأسباب التغيير ومواقعه على GitHub.

## خطوات العمل المنفذة

1. راجعت CODEX_TASK.md والمخطط والمحرك والواجهة واختبارات النسخة السابقة. تأكدت أن جداول الأدوار موجودة لكن لا توجد مصادقة أو بوابة صلاحيات.
2. أبقيت مخطط المحاسبة الأصلي وseed وضوابط الترحيل، وأضفت امتداداً محلياً مستقلاً. وثقت قرار المطابقة بين المخطط القديم والممتد عند الاستعادة.
3. أنشأت الجلسات والأدوار والاستثناءات والملكية والصناديق ثم ربطت بها كل أوامر Android. التحقق داخل Python ويشمل القراءة والكتابة، إلى جانب أزرار الواجهة.
4. ربطت تدقيق المحرك بمنفذ الجلسة، بما في ذلك السداد الآلي. لم أنسب الحركات القديمة مجهولة المنفذ إلى موظف مصطنع.
5. أضفت شاشات إعداد المدير والدخول وإدارة الموظفين وكلمة المرور، والطباعة والتصدير المحكومين بالإذن وقت إخراج الملف.
6. حدثت الاختبارات السابقة لتدخل بحساب مدير فعلي، وأضفت 23 اختباراً أمنياً. لم أحذف اختبارات المحاسبة الـ35.
7. شغلت 78 اختباراً محلياً وفحص تركيب Java وفحص فروق Git؛ النتائج في ملف التحقق. رفعت الكود على فرع العمل لتشغيل بناء Android والمحاكي.

## تصحيحات التحقق المسجلة

كشف مترجم Android أن PdfDocument لا يطبق AutoCloseable. استبدلت try-with-resources بإغلاق صريح في finally؛ ثم نجح بناء APK. فحص تركيب Java المحلي لم يكن بديلاً عن هذا المترجم، لذلك لم أعتبره دليلاً على اكتمال البناء.

أضفت بعدها رفض استيراد نسخة محمية لا تحمل مديراً نشطاً، والتحقق من نوع رقم المستخدم، واختبار بيع فعلي بواسطة الكاشير يثبت UserID وعزل حركاته المالية.

## الكود الكامل والفروق قبل/بعد

- [Commit المصادقة والمحرك والاختبارات](https://github.com/lsrwrbdllh-dot/abud.sQllite/commit/388976e3a71d61c1bf3f1e9fc3c3c4d2dd60c8b7).
- [Commit واجهات Android والبناء واختبار المحاكي](https://github.com/lsrwrbdllh-dot/abud.sQllite/commit/fcd96c715ee9bf4fdc0786fbdc8f62f480c7a556).
- [تصحيح توافق PDF مع Android](https://github.com/lsrwrbdllh-dot/abud.sQllite/commit/c6f9cf1b5c08f5e819de0e853bc6e3696f0d1a2e).
- [حماية الاستعادة واختبار بيع الكاشير](https://github.com/lsrwrbdllh-dot/abud.sQllite/commit/6b98c7fb8d28ac89afb082071b9fb0945c57eef8).
- [كل ملفات طلب السحب](https://github.com/lsrwrbdllh-dot/abud.sQllite/pull/3/files). تبويب Commits يحفظ تسلسل العمل. main لم يعدل مباشرة.

كل سطر كود مضاف أو محذوف ظاهر في الفروق أعلاه؛ الفهرس التالي يشرح غرض الدوال ويحدد موضعها، دون نسخ ثانية للكود قد تصبح قديمة.

## database/mobile_security.py

| الدالة | الموقع | لماذا تغيرت أو أضيفت |
| --- | --- | --- |
| `now` | [السطر 65](../database/mobile_security.py#L65) | توحيد وقت التدقيق UTC. |
| `audit` | [السطر 69](../database/mobile_security.py#L69) | تسجيل المنفذ والتغيير مع حجب كلمات المرور والرموز. |
| `catalog` | [السطر 79](../database/mobile_security.py#L79) | تعريف كل إذن باسم عربي ورمز ثابت. |
| `defaults` | [السطر 95](../database/mobile_security.py#L95) | تحديد البداية المعتمدة للأدوار الخمسة. |
| `ensure` | [السطر 135](../database/mobile_security.py#L135) | ترقية محلية إضافية وإدراج الأدوار والأذونات مرة واحدة دون مسح القاعدة. |
| `configured` | [السطر 153](../database/mobile_security.py#L153) | منع إعادة إنشاء مدير بعد إتمام الإعداد. |
| `password_hash` | [السطر 157](../database/mobile_security.py#L157) | تجزئة كلمة المرور بملح عشوائي وحدود طول موثقة. |
| `verify` | [السطر 164](../database/mobile_security.py#L164) | التحقق من PBKDF2 بالمقارنة الثابتة ورفض التجزئات غير المدعومة. |
| `_path` | [السطر 177](../database/mobile_security.py#L177) | ربط الجلسة بملف القاعدة الصحيح. |
| `invalidate` | [السطر 181](../database/mobile_security.py#L181) | إنهاء جلسات الحساب المتغير أو القاعدة المستعادة. |
| `_session` | [السطر 188](../database/mobile_security.py#L188) | إصدار رمز جلسة عشوائي في الذاكرة. |
| `actor` | [السطر 195](../database/mobile_security.py#L195) | التحقق من الجلسة ونشاط الحساب وتحميل صلاحياته الحالية وإسناد UserID. |
| `has` | [السطر 217](../database/mobile_security.py#L217) | حساب الصلاحية الفعلية للمدير أو الموظف. |
| `check` | [السطر 221](../database/mobile_security.py#L221) | رفض العملية برسالة اسم الصلاحية العربية. |
| `table_check` | [السطر 225](../database/mobile_security.py#L225) | تطبيق إذن الجدول وضوابط التدقيق والتكلفة والأرباح. |
| `columns` | [السطر 235](../database/mobile_security.py#L235) | حجب حقول التكلفة وسعر الشراء. |
| `visible` | [السطر 242](../database/mobile_security.py#L242) | إزالة القيم المحجوبة من الاستجابات نفسها. |
| `pk` | [السطر 246](../database/mobile_security.py#L246) | استخراج مفتاح الجدول من PRAGMA. |
| `scope` | [السطر 250](../database/mobile_security.py#L250) | توحيد مرشح ملكية المستند والصناديق للقوائم والعدادات والبحث والتفاصيل. |
| `accessible` | [السطر 282](../database/mobile_security.py#L282) | فحص نطاق سجل بعينه قبل القراءة أو التعديل أو الربط. |
| `references` | [السطر 293](../database/mobile_security.py#L293) | منع ربط المستند بسجل أو صندوق خارج النطاق. |
| `ownership` | [السطر 300](../database/mobile_security.py#L300) | حفظ منشئ المستند لعرض عملياته وحدها. |
| `bootstrap` | [السطر 305](../database/mobile_security.py#L305) | إنشاء المدير الأول مرة واحدة دون تغيير الأرصدة. |
| `login` | [السطر 322](../database/mobile_security.py#L322) | مصادقة الحساب والتخفيف من تخمين كلمات المرور وتسجيل الدخول. |
| `user_catalog` | [السطر 341](../database/mobile_security.py#L341) | إرجاع بيانات إدارة الحسابات والأذونات دون كلمات المرور. |
| `user_save` | [السطر 355](../database/mobile_security.py#L355) | حفظ الدور والاستثناءات والصناديق وتعطيل الحساب ومنع إزالة آخر مدير والتصعيد. |
| `change_password` | [السطر 416](../database/mobile_security.py#L416) | تغيير كلمة المرور بعد التحقق من الحالية وإنهاء الجلسات. |

## database/mobile_bridge.py

| الدالة | الموقع | لماذا تغيرت أو أضيفت |
| --- | --- | --- |
| `_rows` | [السطر 36](../database/mobile_bridge.py#L36) | تطبيق النطاق والحجب في البيانات والبحث والعدادات معاً. |
| `schema` | [السطر 57](../database/mobile_bridge.py#L57) | إرجاع الجداول والحقول والأزرار المسموحة فقط وملف المستخدم. |
| `_audit` | [السطر 147](../database/mobile_bridge.py#L147) | استخدام سجل موحد يحمل UserID ويحجب الأسرار. |
| `save` | [السطر 150](../database/mobile_bridge.py#L150) | نسب إنشاء المستند إلى الموظف داخل معاملة الحفظ. |
| `restore` | [السطر 212](../database/mobile_bridge.py#L212) | قبول المخطط الأصلي أو الممتد والتحقق قبل الاستبدال وحفظ منفذ الاستعادة في النسخة السابقة. |
| `_authorize` | [السطر 303](../database/mobile_bridge.py#L303) | بوابة واحدة لكل قراءة وكتابة واعتماد وتقرير وطباعة وتصدير وصيانة. |
| `_dispatch` | [السطر 361](../database/mobile_bridge.py#L361) | تشغيل الإعداد والدخول والجلسات وخدمات الموظفين، وإسناد الاعتماد والعكس والجرد، وتطبيق الأذونات على مخرجات الملفات. |

## database/engine.py

| الدالة | الموقع | لماذا تغيرت أو أضيفت |
| --- | --- | --- |
| `__init__` | [السطر 65](../database/engine.py#L65) | إضافة منفذ اختياري دون تغيير API المستخدمين القدامى أو الحسابات. |
| `_finish` | [السطر 232](../database/engine.py#L232) | إسناد اعتماد المستند والسداد التلقائي لمنفذ الجلسة. |
| `manual_entry` | [السطر 592](../database/engine.py#L592) | إسناد القيد اليدوي والعكس لمنفذ الجلسة. |

## واجهة Android

| الدالة | الموقع | الغرض |
| --- | --- | --- |
| `onCreate` | [السطر 43](../android/app/src/main/java/com/abud/supermarket/MainActivity.java#L43) | توجيه القاعدة الموجودة إلى الدخول أو إعداد المدير. |
| `call` | [السطر 56](../android/app/src/main/java/com/abud/supermarket/MainActivity.java#L56) | إرفاق رمز الجلسة بأوامر Python. |
| `request` | [السطر 63](../android/app/src/main/java/com/abud/supermarket/MainActivity.java#L63) | إعادة شاشة الدخول عند انتهاء الجلسة. |
| `welcome` | [السطر 108](../android/app/src/main/java/com/abud/supermarket/MainActivity.java#L108) | إلزام إنشاء حساب المدير عند إنشاء المتجر. |
| `clearSession` | [السطر 118](../android/app/src/main/java/com/abud/supermarket/MainActivity.java#L118) | مسح سياق المستخدم والكتالوج والملفات المؤقتة عند الخروج. |
| `route` | [السطر 119](../android/app/src/main/java/com/abud/supermarket/MainActivity.java#L119) | تمييز متجر جديد وقاعدة تحتاج إعداد مدير وقاعدة تحتاج دخول. |
| `login` | [السطر 119](../android/app/src/main/java/com/abud/supermarket/MainActivity.java#L119) | شاشة دخول أو إعداد مدير. |
| `has` | [السطر 127](../android/app/src/main/java/com/abud/supermarket/MainActivity.java#L127) | تكييف الواجهة مع الأذونات الحساسة. |
| `right` | [السطر 128](../android/app/src/main/java/com/abud/supermarket/MainActivity.java#L128) | قراءة صلاحيات الجدول المفصلة. |
| `password` | [السطر 129](../android/app/src/main/java/com/abud/supermarket/MainActivity.java#L129) | تغيير كلمة المرور وتأكيدها وتسجيل الدخول مجدداً. |
| `users` | [السطر 136](../android/app/src/main/java/com/abud/supermarket/MainActivity.java#L136) | عرض الحسابات وحالتها وأزرار الإدارة. |
| `userForm` | [السطر 144](../android/app/src/main/java/com/abud/supermarket/MainActivity.java#L144) | إدارة الدور والاستثناءات والصناديق والنشاط وإعادة كلمة المرور. |
| `home` | [السطر 178](../android/app/src/main/java/com/abud/supermarket/MainActivity.java#L178) | إظهار أقسام المستخدم المسموحة وإدارة الموظفين والخروج. |
| `list` | [السطر 216](../android/app/src/main/java/com/abud/supermarket/MainActivity.java#L216) | فصل الإضافة والتصدير عن العرض. |
| `detail` | [السطر 233](../android/app/src/main/java/com/abud/supermarket/MainActivity.java#L233) | فصل التعديل والحذف والاعتماد والطباعة والعكس. |
| `reports` | [السطر 350](../android/app/src/main/java/com/abud/supermarket/MainActivity.java#L350) | فصل عرض التقرير وطباعته وتصديره حسب الإذن. |
| `cell` | [السطر 365](../android/app/src/main/java/com/abud/supermarket/MainActivity.java#L365) | تحويل القيم الصحيحة إلى نص دقيق للطباعة والتصدير. |
| `csv` | [السطر 368](../android/app/src/main/java/com/abud/supermarket/MainActivity.java#L368) | بناء CSV من مخرجات مصرح بها وقت الكتابة. |
| `prepareExport` | [السطر 374](../android/app/src/main/java/com/abud/supermarket/MainActivity.java#L374) | حفظ طلب التصدير لإعادة التحقق بعد منتقي الملفات. |
| `print` | [السطر 375](../android/app/src/main/java/com/abud/supermarket/MainActivity.java#L375) | طباعة PDF عبر خدمة Android مع فحص الجلسة والإذن عند onWrite. |
| `printRow` | [السطر 394](../android/app/src/main/java/com/abud/supermarket/MainActivity.java#L394) | تنسيق الحقول والمجاميع والأسطر المسموحة فقط. |
| `maintenance` | [السطر 399](../android/app/src/main/java/com/abud/supermarket/MainActivity.java#L399) | تقييد إنشاء النسخة والاستعادة والفحص وتصدير النسخة السابقة. |
| `onActivityResult` | [السطر 409](../android/app/src/main/java/com/abud/supermarket/MainActivity.java#L409) | إعادة التحقق قبل كتابة الملفات وإعادة الدخول بعد الاستيراد. |

## الملفات الأخرى

| الملف | التغيير وسببه |
| --- | --- |
| [002_mobile_security.sql](../database/migrations/002_mobile_security.sql) | إضافة علامة الإعداد وإصدار الامتداد، واستثناءات الموظف وصناديقه وملكية مستنداته؛ مع FK وCHECK ومفاتيح وفهرس للملكية. لا تعديل على الجداول أو triggers الأصلية. |
| [app/build.gradle](../android/app/build.gradle) | الإصدار 1.1.0 / code 2؛ تضمين mobile_security.py ومهاجرة الامتداد داخل APK. |
| [test_mobile_bridge.py](../tests/test_mobile_bridge.py) | دخول المدير في جميع اختبارات JSON؛ استبدال CRUD العام لجداول الأمان بخدمة إدارة المستخدمين المحكومة، مع اختبار رفض تعديلها العام. |
| [test_mobile_security.py](../tests/test_mobile_security.py) | 23 سيناريو من واجهة الأوامر الفعلية: جلسات وأدوار ومنع تصعيد وعزل بيانات وحجب تكلفة وأذونات حساسة وتدقيق وترقية ونسخ واستعادة. |
| [android_offline_smoke.py](../tests/android_offline_smoke.py) | إعداد مدير دون شبكة، ترحيل قيد، استمرار البيانات، طلب الدخول بعد إعادة العملية، إنشاء كاشير والدخول به والتأكد من عدم ظهور أقسامه الممنوعة. |
| [android-mobile.yml](../.github/workflows/android-mobile.yml) | تسمية خطوة التحقق بما تعمله الآن؛ يستمر منع نشر APK قبل نجاح الاختبارات والمحاكي. |
| [دليل الصلاحيات](employee-permissions.md) | التشغيل والتهيئة والأدوار والتخصيص والضوابط وحدود الملف المحلي والتوقيع والاستيراد. |
| [سجل الاختبارات](validation/employee-permissions-unittest.txt) | خرج الاختبارات الفعلي؛ لا يتضمن بيانات متجر حقيقية أو أسرار دخول. |
| README.md / android/README.md / ابدأ-الجوال.txt / mobile-build-status.md | تحديث طريقة التشغيل وحدود النسخة وحالة الاختبار؛ تمييز APK السابق عن الإصدار الجديد. |

## نتائج التحقق وحدودها

نجحت 78 حالة اختبار محلياً. فحص Java المحلي هو تحليل تركيب فقط؛ نتيجة ترجمة Android واختبار الواجهة الفعليين تحفظ في حالة البناء بعد انتهاء GitHub Actions. لم يجر اختبار على هاتف المالك الفعلي. لا توجد معاملات مالية حقيقية في بيانات الاختبار.
