$(function () {
    var widget = document.querySelector('#cap');

    if (widget) {
        widget.addEventListener('solve', function (e) {

            var capToken = e.detail?.token || '';
            $('#CapToken').val(capToken);
            /* console.log('CapSolved:', capToken)*/
            $("#error-captxt").addClass("d-none");
        });
        widget.addEventListener('reset', function () {
            $('#CapToken').val('');
            /*  console.log('Captjs reset');*/
        });
    }
});

$(function () {
    function loadCaptcha() {
        $.ajax({
            url: '/Barname/Captcha/Generate',
            type: 'GET',
            success: function (res) {
                if (!res.success) {
                    toaster.toast("error", "پیغام خطا", "خطا در دریافت کپچا");
                    return;
                }
                // تصویر
                $('#captchaImage')
                    .attr('src', res.image)
                    .fadeIn(150);
                // توکن
                $('#captchaToken').val("");
                $('#captchaToken').val(res.token);

                // پاک کردن جواب قبلی
                $('#CaptchaCode').val("");
            },
            error: function () {
                toaster.toast("error", "پیغام خطا", "خطا در ارتباط با سرور");
            }
        });
    }

    // بارگذاری اولیه
    loadCaptcha();

    // رفرش دستی
    $('#btnReloadCaptcha').on('click', function () {
        loadCaptcha();
    });

});
/**********************************************/
$(function () {
    // مقدار را اینجا تنظیم کن: "rtl" یا "ltr"
    const direction = "rtl";

    const $boxes = $(".otp-box");
    const $hidden = $("#otp");

    // index helpers
    const idx = el => $boxes.index(el);
    const getBoxAt = i => $boxes.eq(i);
    const lastIndex = () => $boxes.length - 1;

    // شروع فوکوس: بر اساس جهت
    if ($boxes.length) {
        if (direction === "rtl") {
            // focus روی آخرین باکس (سمت راستِ بصری)
            getBoxAt(lastIndex()).focus().select();
        } else {
            // ltr: اولین باکس
            getBoxAt(0).focus().select();
        }
    }

    // وقتی یک باکس ورودی می‌پذیرد
    $boxes.on("input", function () {
        const $box = $(this);
        // فقط عدد بگذار
        $box.val($box.val().replace(/\D/g, ""));

        // اگر یک رقم وارد شده، حرکت کن
        if ($box.val().length === 1) {
            const current = idx(this);
            let nextIndex = (direction === "rtl") ? current - 1 : current + 1;
            if (nextIndex >= 0 && nextIndex <= lastIndex()) {
                getBoxAt(nextIndex).focus().select();
            } else {
                // اگر به انتها رسیدیم، خود را select کن (برای راحتی)
                $box.select();
            }
        }

        updateHidden();
    });

    // backspace: وقتی خالیست و backspace زده شد → حرکت به باکس قبلی (بر اساس جهت)
    $boxes.on("keydown", function (e) {
        if (e.key === "Backspace") {
            const $this = $(this);
            const current = idx(this);

            // اگر داخل همین باکس کاراکتری هست، معمولاً حذف میشه — رفتار عادی
            // اما اگر خالی بود، باید به باکس قبلی حرکت کنیم
            if ($this.val().length === 0) {
                // در RTL قبلی یعنی حرکت به راست، در LTR حرکت به چپ
                let prevIndex = (direction === "rtl") ? current + 1 : current - 1;
                if (prevIndex >= 0 && prevIndex <= lastIndex()) {
                    e.preventDefault(); // جلوگیری از رفتار پیش‌فرض (در صورت نیاز)
                    const $prev = getBoxAt(prevIndex);
                    $prev.focus().select();
                    // حذف کاراکتر قبلی اگر مایل بودی می‌تونی اینجا انجام بدی:
                    // $prev.val(''); updateHidden();
                }
            }
        }
    });

    // اجازه‌ی paste کردن یکبار برای کل کد (اگر کاربر paste کرد: اعداد را به باکس‌ها بریز)
    $boxes.on("paste", function (e) {
        e.preventDefault();
        const paste = (e.originalEvent || e).clipboardData.getData('text') || '';
        const digits = paste.replace(/\D/g, '').split('');
        if (!digits.length) return;

        if (direction === "rtl") {
            // از راست به چپ پر کن (ابتدا آخرین باکس)
            let i = lastIndex();
            for (let d of digits) {
                if (i < 0) break;
                getBoxAt(i).val(d);
                i--;
            }
        } else {
            // ltr: از ابتدا پر کن
            let i = 0;
            for (let d of digits) {
                if (i > lastIndex()) break;
                getBoxAt(i).val(d);
                i++;
            }
        }
        updateHidden();
        // فوکوس را به اولین غیرپر یا آخرین المنت بده
        if (direction === "rtl") {
            const firstNotFilled = $boxes.toArray().findIndex(b => $(b).val().length === 0);
            if (firstNotFilled === -1) getBoxAt(0).focus().select();
            else getBoxAt(firstNotFilled).focus().select();
        } else {
            const firstNotFilled = $boxes.toArray().findIndex(b => $(b).val().length === 0);
            if (firstNotFilled === -1) getBoxAt(lastIndex()).focus().select();
            else getBoxAt(firstNotFilled).focus().select();
        }
    });

    function updateHidden() {
        // اگر RTL هستیم، معمولاً می‌خواهیم مقدار نهایی از راست به چپ خوانده شود
        // (مثلاً باکس‌های DOM از چپ→راست باشند ولی مقدار OTP منطقی از راست→چپ)
        // من اینجا برای RTL مقدار را از راست به چپ join می‌کنم (درصورت نیاز تغییر بده)
        let code;
        if (direction === "rtl") {
            // ترتیب برداشت: از آخرین به اولین
            code = $boxes.map(function () { return $(this).val(); }).get().reverse().join("");
        } else {
            code = $boxes.map(function () { return $(this).val(); }).get().join("");
        }
        $hidden.val(code);
    }

});
/**********************************************/
var IsDraft = false;
const apiKey = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsImp0aSI6Ijg5ZWQwM2Q4MjVmMDA3NTcwMjg5ZTk0MDBjODM5ZDZjMjlhZGZmNDkzOGJhZDEzNmFjZDJmNWU5ODRmMGVmODZkOWUzNWRkMWRhYzc1YmJkIn0.eyJhdWQiOiIzMTc3OCIsImp0aSI6Ijg5ZWQwM2Q4MjVmMDA3NTcwMjg5ZTk0MDBjODM5ZDZjMjlhZGZmNDkzOGJhZDEzNmFjZDJmNWU5ODRmMGVmODZkOWUzNWRkMWRhYzc1YmJkIiwiaWF0IjoxNzQzODQwNDgzLCJuYmYiOjE3NDM4NDA0ODMsImV4cCI6MTc0NjQzMjQ4Mywic3ViIjoiIiwic2NvcGVzIjpbImJhc2ljIl19.bF09k01by6d5eFveNe1VEMBTKvjt_c8msj6fn7G3XzwY3RFcTIwGPw5JgkJ_NwSKO0byOEPB-KsNwuW1_E9sC2y_KRchX877MSzCtrpx5Nid5bnxWonf-0-0JvRZqGAA5yQaTJoZfq102fqnjKJNp8M2c2RM99pWCg--wf_aE15RCX-K02L1qQOsa3W6wasc7ZTBd3wOf-8gJIWCcBBbh8kA_zd-mgBvWP4g754shCzH3NXJFdCpdmTPDbGNK0qLbb9zn4R3QleTtDfMoG9LF3TI7bkpbTLMEuJsSxm_xQ0KO_6Vxrn4tpb0396NeGz-nJRzBjM6fpE041hTpHQxMQ';

var suc = "";
var appMap = null;
var objid = null;
var appMap2 = null;
var appMap3 = null;
var pelakv = 1;
var ddSender = 0;
var ddReceiver = 0;
var ucv01 = 1;
var LicenseNumber = 0;
var txtWeight = "";
var txtLoadName = "";
var txtLoadDetail = "";
var ddBoxType = "";
var boxTypeList = [];
var select_style_text = "";
var selecteditme = "";
var chkInsurance = [];
var txtLoadsValue = [];
var txtBoxNum = [];
var cityDoc = null;
var useriddriver = 0;
var truckid = 0;
var txtSenderFirstName = 0;
var txtSenderLastName = 0;
var txtSenderMobile = 0;
var txtSenderNationalCode = 0;
var txtReceiverFirstName = 0;
var txtReceiverLastName = 0;
var txtReceiverMobile = 0;
var txtReceiverNationalCode = 0;
var ddTruck = 0;
var ddDriver = 0;
var chkInsurance = false;
var txtLoadsValue = 0;
var ddStateSource = 0;
var ddCitySource = 0;
var txtAddressSource = 0;
var ddStateDest = 0;
var ddCityDest = 0;
var txtAddressDest = 0;
var txtnotifyCost = 0;
var txtAvarez = 0;
var txtbearingCost = 0;
var txtIT_Cost = 0;
var txtRemainCredit = 0;
var txtTotalPay = 0;
var selectedboxtype = 0;
var LatSource = "";
var idSender = 0;
var idKala = 0;
var txtPlaqueSearch = 0;
var pelakTypeCombo = 0;
var rqsSecondThreeNo = 0;
var rqsIRTwoNo = 0;
var rqsFirstTwoNo = 0;
var rqsCharacterNo = 0;
var haveCertificate = false;
var source = "";
var idAddress = "";
var AddressState = "";
var AddressCity = "";
var Address = "";
var firstName = "";
var lastName = "";
var havelicense = false;
var have3rd = "";
var numberLoad = 0;
var havecertificateinload = 0;
var totalWeight = 0;
var capacityTo = 0;
var pelakitem = "";
var CapacityTajmiglobal = 0;
var CapacityTajmiTo = 0;
var CapaUnit = 0;
///////////////////////////
var loadList = [];
/////////////////////////
var IT_cost = 0;
var RowID = 0;
var avarez = 0;
var bearingCost = 0;
var canIssue = 0;
var date = 0;
var dateFarsi = 0;
var destAddress = 0;
var destCityId = 0;
var destCityName = 0;
var destPostalCode = 0;
var destStateId = 0;
var destStateName = 0;
var docNo = 0;
var driverCertificateNumber = 0;
var driverFirstName = 0;
var driverFullName = 0;
var driverHaveCertificate = 0;
var driverImage = 0;
var driverLastName = 0;
var driverMobile = 0;
var driverNationalCode = 0;
var driverRank = 0;
var id = 0;
var insurance = 0;
var loadDescription = 0;
var loadId = 0;
var loadName = 0;
var loadTypeName = 0;
var loadWeight = 0;
var notifyCost = 0;
var packTypeId = 0;
var packTypeName = 0;
var postRent = 0;
var preRent = 0;
var receiverFirstName = 0;
var receiverLastName = 0;
var ReceiverOfficeName = 0;
var receiverMobile = 0;
var receiverNationalCode = 0;
var receiverPostalCode = 0;
var receiverTelNumber = 0;
var rent = 0;
var rowData = 0;
var senderFirstName = 0;
var senderLastName = 0;
var SenderOfficeName = 0;
var senderMobile = 0;
var senderNationalCode = 0;
var senderPostalCode = 0;
var senderTelNumber = 0;
var sourceAddress = 0;
var sourceCityId = 0;
var sourceCityName = 0;
var sourcePostalCode = 0;
var sourceStateId = 0;
var sourceStateName = 0;
var LatSource = "";
var LngSource = "";
var LatDestination = "";
var LngDestination = "";
var status = 0;
var statusName = 0;
var submitterId = 0;
var t1 = 0;
var t2 = 0;
var t3 = 0;
var t4 = 0;
var tag = 0;
var time = 0;
var toPay = 0;
//نمایش پلاک ها بصورت حروف
var rest1 = "";
var rest2 = "";
var rest3 = "";
var rest4 = "";
var truckCapacity = 0;
var truckCapacityTo = 0;
var truckHave3rdInsurance = false;
var truckHaveCertificate = false;
var truckId = 0;
var truckTagType = false;
var truckType = 0;
var type = 0;
var userIdDriver = 0;
var value = 0;
var value1 = 0;
var zoneCityIds = 0;
var zoneStateIds = 0;
////////////////////////
var PostalCode = "";
var dateInsert = "";
var btnaddLoadNumber = 0;
var pelas = 0;
var mainez = 0;
var pelasModal = 0;
var mainezModal = 0;
var idload = 0;
var idPelak = 0;
var idDocument = 0;
var myDataTableLoad = 0;
var insertvalue = "0";
var insuranceValue = 0;
var t1forLoad = null;
var t2forload = null;
var t3forload = null;
var t4forload = null;
var DriverMobile = 0;
var DriverSearchv = 0;
var selectpelak = 0;
var btnRegPelak = 0;
var btnRegDriver = 0;
//جهت مدیریت خطا هادر هر ویزارد 
var stepSource = 0;
var stepDest = 0;
var fuelType = 0;
var SendSMS = false;
var SMSvalue = false;
var notifyCosttxt = 0;
var myDataTablePelak = "";
var GlobalTajmiiFlag = null;
let GlobalfreighterId = null;
let pelaktype = null;
//مقادیر پلاک تجمیع
let tajmiT1 = null;
let tajmiT2 = null;
let tajmiT3 = null;
let tajmiT4 = null;

//Source Address
let mapFlagSourceCityId = "";
let mapFlagSourceCityTitle = "";
let mapFlagSourceAddress = "";
let mapFlagSourcePostalCode = "";
let mapFlagSourceStateId = "";
let mapFlagSourceStateTitle = "";

//Destination Address
let mapFlagDestinationCityId = "";
let mapFlagDestinationCityTitle = "";
let mapFlagDestinationAddress = "";
let mapFlagDestinationPostalCode = "";
let mapFlagDestinationStateId = "";
let mapFlagDestinationStateTitle = "";

let mapFlag = true;
let mapFlagShow = false;
let ddCitySourceId = 0;
let ddCityDestId = 0;

let citySourceMap = "";
let CityDestMap = "";

var objformhelper = new formHelper();
let IsTrueCode = false;

let PlaceSource = {
    Name: '',
    StateName: '',
    CityName: '',
    Address: '',
    PostalCode: '',
    Lat: '',
    Lon: '',
    Primary: '',
    Poi: '',
    Country: '',
    County: '',
    District: '',
    Village: '',
    Region: '',
    Neighbourhood: '',
    Last: '',
    Plaque: ''
}
let PlaceDestination = {
    Name: '',
    StateName: '',
    CityName: '',
    Address: '',
    PostalCode: '',
    Lat: '',
    Lon: '',
    Primary: '',
    Poi: '',
    Country: '',
    County: '',
    District: '',
    Village: '',
    Region: '',
    Neighbourhood: '',
    Last: '',
    Plaque: ''
}
//زمان تایمر کد احرازهویت
var otpDuration = 0;
//لیست ماشین و اطلاعات کمبو
var CarList = [];



var DetailsHtml = '<div class="form-group col-md-12 mt-2">'
    + '<label class="col-sm-3 col-xs-12 ">کالا</label>'
    + '<div class="col-sm-9 col-xs-12"><label id="rqsLoadName" name="rqsLoadName" class="control-label rqsLoadName heightStyle"style="border-bottom: 1px solid #a6e1ec; "></label></div>'
    + '</div>'
    + '<div class="form-group col-md-12 mt-2">'
    + '<label class="col-sm-3  col-xs-12 ">وزن بار</label>'
    + '<div class="col-sm-9 col-md-9 col-xs-12"><label id="rqsWeight" name="rqsWeight" class=" control-label rqsLoadName heightStyle"style="border-bottom: 1px solid #a6e1ec; "></label></div>'
    + '</div>';

$(function () {

    $("#pelakCombo1").val('');
    FormDocumenDetailsRegister();

});



//نمایش نقشه برای مبدا در صورت فعال بودن MapFlag
function RevereseMapLatSource(LatSource, LngSource) {

    $.ajax({
        /* url: "/Account/FormDocumentDetailsRegister.aspx",*/
        url: "/Barname/Document/RevereseMap",
        function: "RevereseMap",
        data: {
            lat: LatSource,
            lon: LngSource,
        },
        success: function (Doc) {


            $("#loading").hide();
            if (Doc.resultCode == 200) {
                /*  var result = JSON.parse(Doc.obj);*/
                let result = Doc.obj;
                $("#txtAddressSource").val(result.address_compact);
                $("#txtAddressSourceFromMap").val(result.address_compact);
                $("#SourcePostalCodeFromMap").val(result.sourcePostalCode);
                $("#txtAddressSourceView").val(result.address_compact);
                $("#ddStateSource").val(result.province);
                
                citySourceMap = result.city == "" ? result.county : result.city

                $("#ddCitySource").val(citySourceMap);
                $("#Postal_code").val(result.sourcePostalCode);
                $("#SourcePostalCodeView").val(result.sourcePostalCode);

            }
            else {
                toaster.toast("error", "خطا", Doc.resultMessage)

            }

        },
        error: function (error) {
            $("#loading").hide();
            toaster.toast("error", "خطا", error.statusText)

        }
    });


}
function showmapSource() {

    let defaultalat = 35.748564;
    let defaultalng = 51.371990;

    let initLat = LatSource ? LatSource : defaultalat;
    let initLng = LngSource ? LngSource : defaultalng;

    
    if (appMap == null) {
        appMap = new Mapp({
            element: '#MapSource',
            presets: {
                latlng: {
                    lat: initLat,
                    lng: initLng,
                },
                zoom: 15
            },
            apiKey: apiKey

        });

        appMap.addLayers();
        

        setTimeout(function () {

            appMap.addZoomControls();
        }, 3000)




        var middleIcon = {
            iconUrl: 'https://cdn.map.ir/web-sdk/1.4.2/assets/images/marker-start-route.png',
            iconSize: [35, 35],
            iconAnchor: [10, 10],
        };
        appMap.addMarker({

            latlng: {
                lat: initLat,
                lng: initLng,
            },
            popup: false,
            icon: middleIcon,
        });

        appMap.map.invalidateSize();


        if (!!LatSource) {

        }


        appMap.map.on('move', function (e) {
            /*crosshairMarker.setLatLng(appMap.getCenter());*/
        })

        appMap.map.on('click', function (e) {


            // آدرس یابی و نمایش نتیجه در یک باکس مشخص
            //var crosshairIcon = {
            //    iconUrl: '../Scripts/MainScript/MapFile/assets/images/icongreen.png',
            //    iconSize: [37, 37], // size of the icon
            //    iconAnchor: [37, 37], // point of the icon which will correspond to marker's location
            //};
            var middleIcon = {
                iconUrl: 'https://cdn.map.ir/web-sdk/1.4.2/assets/images/marker-start-route.png',
                iconSize: [35, 35],
                iconAnchor: [10, 10],
            };
            appMap.addMarker({
                /*  name: 'Point',*/
                latlng: {
                    lat: e.latlng.lat,
                    lng: e.latlng.lng,
                },
                popup: false,
                icon: middleIcon,
            });
            $("#loading").show();
            $.ajax({
                /* url: "/Account/FormDocumentDetailsRegister.aspx",*/
                url: "/Barname/Document/RevereseMap",
                function: "RevereseMap",
                data: {
                    lat: e.latlng.lat,
                    lon: e.latlng.lng
                },
                success: function (Doc) {

                    LatSource = e.latlng.lat;
                    LngSource = e.latlng.lng;
                    $("#loading").hide();
                    if (Doc.resultCode == 200) {
                        /*  var result = JSON.parse(Doc.obj);*/
                        let result = Doc.obj;
                        $("#txtAddressSource").val(result.address_compact);
                        $("#txtAddressSourceFromMap").val(result.address_compact);
                        $("#SourcePostalCodeFromMap").val(result.sourcePostalCode);
                        $("#txtAddressSourceView").val(result.address_compact);
                        $("#ddStateSource").val(result.province);

                        $("#rqsOrigin").val(result.city == "" ? result.county : result.city);
                        $("#SourcePostalCodeFromMap").val(result.sourcePostalCode);
                        $("#ddCitySource").val(result.city);
                        citySourceMap = result.city == "" ? result.county : result.city
                        $("#Postal_code").val(result.sourcePostalCode);
                        $("#SourcePostalCodeView").val(result.sourcePostalCode);
                        ///---------- Set Value For Place Object ----------
                        PlaceSource.Address = result.address;
                        PlaceSource.CityName = citySourceMap;
                        if (result != null && result.geom != null && result.geom.coordinates != null) {
                            PlaceSource.Lat = result.geom.coordinates[1];
                            PlaceSource.Lon = result.geom.coordinates[0];
                        }
                        PlaceSource.Country = result.country;
                        PlaceSource.County = result.county;
                        PlaceSource.District = result.district;
                        PlaceSource.Last = result.last;
                        PlaceSource.Name = result.name;
                        PlaceSource.Neighbourhood = result.neighbourhood;
                        PlaceSource.Plaque = result.plaque;
                        PlaceSource.Poi = result.poi;
                        PlaceSource.Postal_code = result.postal_code;
                        PlaceSource.Village = result.village;
                        PlaceSource.Primary = result.primary;
                        PlaceSource.Region = result.region;
                        PlaceSource.StateName = result.province;
                        PlaceSource.PostalCode = result.postal_code;
                    }
                    else {
                        toaster.toast("error", "خطا", Doc.resultMessage)

                    }

                },
                error: function (error) {
                    $("#loading").hide();
                    toaster.toast("error", "خطا", error.statusText)

                }
            });
        });

        setTimeout(function () {

            appMap.map.setView([initLat, initLng], 15);
        }, 3000)
    }

    appMap.map.invalidateSize();
}

//نمایش نقشه برای مقصد در صورت فعال بودن MapFlag
function RevereseMapLatDest(LatDestination, LngDestination) {
    $.ajax({
        /* url: "/Account/FormDocumentDetailsRegister.aspx",*/
        url: "/Barname/Document/RevereseMap",
        function: "RevereseMap",
        data: {
            lat: LatDestination,
            lon: LngDestination,
        },
        success: function (Doc) {


            $("#loading").hide();
            if (Doc.resultCode == 200) {
                let result = Doc.obj;
                $("#txtAddressDest").val(result.address_compact);
                $("#txtAddressDestFromMap").val(result.address_compact);
                $("#destPostalCodeFromMap").val(result.DestPostalCode);
                $("#txtAddressDestView").val(result.address_compact);
                $("#ddStateDest").val(result.province);

                CityDestMap = result.city == "" ? result.county : result.city
                $("#ddCityDest").val(CityDestMap);
                $("#destPostalCode").val(result.DestPostalCode);
                $("#DestPostalCodeView").val(result.DestPostalCode);

            }
            else {
                toaster.toast("error", "خطا", Doc.resultMessage)

            }

        },
        error: function (error) {
            $("#loading").hide();
            toaster.toast("error", "خطا", error.statusText)

        }
    });


}
function showmapDest() {

    if (appMap2 == null) {
        appMap2 = new Mapp({
            element: '#MapDestination',
            presets: {
                latlng: {
                    lat: 35.748564,
                    lng: 51.371990,
                },
                zoom: 15
            },
            apiKey: apiKey

        });

        appMap2.addLayers();
        setTimeout(function () {

            appMap2.addZoomControls();
        }, 3000)




        //var crosshairIcon = L.icon({
        //    iconUrl: 'https://cdn.map.ir/web-sdk/1.4.2/assets/images/marker-start-route.png',
        //    iconSize: [40, 40],
        //    iconAnchor: [10, 10],
        //});
        //var crosshairMarker = new L.marker(appMap.map.getCenter(), { icon: crosshairIcon, clickable: true });
        //crosshairMarker.addTo(appMap.map);

        var middleIcon = {
            iconUrl: 'https://cdn.map.ir/web-sdk/1.4.2/assets/images/marker-end-route.png',
            iconSize: [35, 35],
            iconAnchor: [10, 10],
        };
        appMap2.addMarker({
            /*  name: 'Point',*/
            latlng: {
                lat: 35.748564,
                lng: 51.371990,
            },
            popup: false,
            icon: middleIcon,
        });



        appMap2.map.on('move', function (e) {
            /*crosshairMarker.setLatLng(appMap.getCenter());*/
        })
        //crosshairMarker.on('click', function (event) {
        //    console.log(event.latlng)
        //});
        appMap2.map.on('click', function (e) {


            // آدرس یابی و نمایش نتیجه در یک باکس مشخص
            //var crosshairIcon = {
            //    iconUrl: '../Scripts/MainScript/MapFile/assets/images/icongreen.png',
            //    iconSize: [37, 37], // size of the icon
            //    iconAnchor: [37, 37], // point of the icon which will correspond to marker's location
            //};

            var middleIcon = {
                iconUrl: 'https://cdn.map.ir/web-sdk/1.4.2/assets/images/marker-start-route.png',
                iconSize: [35, 35],
                iconAnchor: [10, 10],
            };
            appMap2.addMarker({
                /*  name: 'Point',*/
                latlng: {
                    lat: e.latlng.lat,
                    lng: e.latlng.lng,
                },
                popup: false,
                icon: middleIcon,
            });
            $("#loading").show();
            $.ajax({
                /* url: "/Account/FormDocumentDetailsRegister.aspx",*/
                url: "/Barname/Document/RevereseMap",
                function: "RevereseMap",
                data: {
                    lat: e.latlng.lat,
                    lon: e.latlng.lng
                },
                success: function (Doc) {

                    LatDestination = e.latlng.lat;
                    LngDestination = e.latlng.lng;
                    $("#loading").hide();
                    if (Doc.resultCode == 200) {
                        /*  var result = JSON.parse(Doc.obj);*/
                        let result = Doc.obj;
                        $("#txtAddressDest").val(result.address_compact);
                        $("#txtAddressDestFromMap").val(result.address_compact);
                        $("#destPostalCodeFromMap").val(result.DestPostalCode);
                        $("#txtAddressDestView").val(result.address_compact);
                        $("#ddStateDest").val(result.province);
                        //ست کردن مقدار شهر  از نقشه
                        $("#rqsDestination").val(result.city == "" ? result.county : result.city);

                        CityDestMap = result.city == "" ? result.county : result.city;

                        $("#ddCityDest").val(CityDestMap);
                        $("#destPostalCode").val(result.DestPostalCode);
                        $("#DestPostalCodeView").val(result.DestPostalCode);
                        PlaceDestination.Address = result.address;
                        PlaceDestination.CityName = result.city;
                        if (result != null && result.geom != null && result.geom.coordinates != null) {
                            PlaceDestination.Lat = result.geom.coordinates[1];
                            PlaceDestination.Lon = result.geom.coordinates[0];
                        }
                        PlaceDestination.Country = result.country;
                        PlaceDestination.County = result.county;
                        PlaceDestination.District = result.district;
                        PlaceDestination.Last = result.last;
                        PlaceDestination.Name = result.name;
                        PlaceDestination.Neighbourhood = result.neighbourhood;
                        PlaceDestination.Plaque = result.plaque;
                        PlaceDestination.Poi = result.poi;
                        PlaceDestination.Postal_code = result.postal_code;
                        PlaceDestination.Village = result.village;
                        PlaceDestination.Primary = result.primary;
                        PlaceDestination.Region = result.region;
                        PlaceDestination.StateName = result.province;
                        PlaceDestination.PostalCode = result.postal_code;
                    }
                    else {
                        toaster.toast("error", "خطا", Doc.resultMessage)

                    }

                },
                error: function (error) {
                    $("#loading").hide();
                    toaster.toast("error", "خطا", error.statusText)

                }
            });
        });



    }


}

function formInitSendOtpCode() {

    objformhelper.init("FormSendOtpCode");
}
///تایمر کد احراز هویت
function startTimer(duration, display, stop) {
    let timer = duration, minutes, seconds;
    var intervals = [];
    let sendNotTimer = setInterval(function () {

        minutes = parseInt(timer / 60, 10);
        seconds = parseInt(timer % 60, 10);

        minutes = minutes < 10 ? "0" + minutes : minutes;
        seconds = seconds < 10 ? "0" + seconds : seconds;

        display.textContent = minutes + ":" + seconds;

        if (timer < 0) {
            $('#time').text("00:00");
            $("#sendVerificationCode").removeClass("visually-hidden");
            $("#submitOtp").addClass("visually-hidden");
            /*$("#Verifyplace").addClass("visually-hidden");*/
            IsTrueCode = false;
            clearInterval(sendNotTimer);
            /*timer = stop;*/
        }
        --timer
    }, 1000);
    intervals.push(sendNotTimer);
    if (stop) {

        intervals.forEach(clearInterval);
    }

}
function downTime(stop) {

    $("#time").text(otpDuration);
    let OtpMinutes = 60 * otpDuration,
        display = document.querySelector('#time');
    startTimer(OtpMinutes, display, stop);
};
//ارسال مجدد کد احراز هویت
$("#sendVerificationCode").on("click", function () {

    $("#loading").show()
    $.ajax({
        url: '/Barname/History/ResendOtpForIssueDocumen',
        type: "POST",
        data: { "documentId": $("#DocumentId").val() },
        success: function (res) {

            if (res.resultCode == 200) {
                $("#sendVerificationCode").addClass("visually-hidden");
                $("#submitOtp").removeClass("visually-hidden");
                $("#Verifyplace").removeClass("visually-hidden");
                $("#loading").hide();
                IsTrueCode = true;
                downTime(false);

            } else {
                $("#loading").hide();
                toaster.toast('error', 'پیغام خطا', res.resultMessage);
            }
        },
        error: function (error) {
            $("#loading").hide();
            toaster.toast('error', 'پیغام خطا', res.resultMessage);
            $("#Allcheckbox").prop('checked', false);
        }
    });

});
//ثبت کد دومرحله ای
$("#submitOtp").on("click", function () {

    objformhelper.validate.init("FormSendOtpCode")

        .success(function () {
            /* if (IsTrueCode == true) {*/
            SendOtpCode()
            //} else {
            //    toaster.toast('error', 'پیغام خطا', 'کد فعال سازی ارسال نشده است');
            //}
        })
        .error(function (error) {

            return false;
        });

});
///ثبت کد احراز هویت
function SendOtpCode() {


    $.ajax({
        url: '/Barname/Document/IssueDocumentByOtpNew',
        type: "POST",
        data: { "docId": $("#DocumentId").val(), "code": $("#otp").val() },
        success: function (res) {

            if (res.resultCode == 200) {
                toaster.toast('success', 'پیغام سامانه ', res.resultMessage);
                if ($("#CapType").val() == 0) {

                    window.cap.reset();
                } else if ($("#CapType").val() == 2) {
                    $("#btnReloadCaptcha").click();
                }
                else if ($("#CapType").val() == 1) {
                    $("#dntCaptchaRefreshButton").click();
                }
                $("#GetOptCodeModal").modal('hide');
                $("#otp").val("");
                $('#time').text("00:00");
                $("#sendVerificationCode").removeClass("visually-hidden");
                $("#submitOtp").addClass("visually-hidden");

                downTime(true);


                /*let success = res.data;*/
                if (res.resultCode == 200) {
                    if (IsDraft) {
                        toaster.toast("success", "موفق", "فایل پیش نویس با موفقیت افزوده شد");
                        if ($("#CapType").val() == 0) {

                            window.cap.reset();
                        } else if ($("#CapType").val() == 2) {
                            $("#btnReloadCaptcha").click();
                        }
                        else if ($("#CapType").val() == 1) {
                            $("#dntCaptchaRefreshButton").click();
                        }
                    }
                    else {
                        objid = res.obj;

                        $.ajax({
                            url: "/Barname/Document/showTrackingCode",
                            function: "showTrackingCode",
                            data: {
                                id: objid
                            },
                            success: function (result) {

                                $("#loading").hide();
                                $("#TrackingCodeNumber").val(result);
                                /* $("#TrackingCodeNumber").text(result);*/
                            },
                            error: function (error) {

                                $("#loading").hide();
                                toaster.toast("error", "خطا", "مشکلی در دریافت کد رهگیری پیش آمده است")
                                return false;
                            }
                        });
                        $("#GoFinalStep").click();
                        $("#pills-tab").addClass("d-none");
                    }

                }
                else {

                    toaster.toast("error", "خطا", res.resultMessage);
                    if ($("#CapType").val() == 0) {

                        window.cap.reset();
                    } else if ($("#CapType").val() == 2) {
                        $("#btnReloadCaptcha").click();
                    }
                    else if ($("#CapType").val() == 1) {
                        $("#dntCaptchaRefreshButton").click();
                    }
                }

            } else {

                toaster.toast('error', 'پیغام خطا', res.resultMessage);
                if ($("#CapType").val() == 0) {

                    window.cap.reset();
                } else if ($("#CapType").val() == 2) {
                    $("#btnReloadCaptcha").click();
                }
                else if ($("#CapType").val() == 1) {
                    $("#dntCaptchaRefreshButton").click();
                }
                return false;
            }
        },
        error: function (error) {

            toaster.toast('error', 'پیغام خطا', error.responseText);
            $("#Allcheckbox").prop('checked', false);
            if ($("#CapType").val() == 0) {

                window.cap.reset();
            } else if ($("#CapType").val() == 2) {
                $("#btnReloadCaptcha").click();
            }
            else if ($("#CapType").val() == 1) {
                $("#dntCaptchaRefreshButton").click();
            }
        }
    });

};

formInitSendOtpCode();


$(document).ready(function () {

    //زمان خوداظهاری شروع حمل
    $(function () {
        var toDay = new Date();
        toDay.setHours(0, 0, 0, 0);

        $("#loadingDate").persianDatepicker({
            format: 'YYYY/MM/DD',
            initialValue: true,
            minDate: toDay,
            maxDate: toDay,
            autoClose: true,
            calendarType: 'persian',
            calendar: {
                persian: {
                    //برای رفع مشکل سال کبیسه
                    leapYearMode: "astronomical",
                    locale: 'en'
                }
            },

            onSelect: function (unixDate) {

                var selectedDate = new Date(unixDate);
                var now = new Date();
            }

        });

        $('#loadingTime').persianDatepicker({
            format: 'HH:mm',
            autoClose: true,
            minDate: new Date(),
            onlyTimePicker: true,
            enableTimePicker: true,
            calendar: {
                persian: {
                    //برای رفع مشکل سال کبیسه
                    leapYearMode: "astronomical",
                    locale: 'en'
                }
            },

            onSelect: function (unixDate) {

                var selectedDate = new Date(unixDate);
                var now = new Date();

                var toDayStr = new persianDate().format('YYYY/MM/DD');
                toDayStr = toDayStr.replace(/[0-9]/g, d => '0123456789'.indexOf(d));
                var selectedStr = new persianDate(selectedDate).format('YYYY/MM/DD');


                //let selecttagvim = $("#loadingDate").val();  //مقدار انتخابی از تقویم

                //let DateNoww = new Date().toLocaleString('fa-IR-u-nu-latin', { year: "numeric", month: "2-digit", day: "2-digit" });  //تاریخ روز جاری


                //ساعت و دقیقه جاری
                let hour = new Date().toLocaleTimeString('en-GB', {
                    hour: "numeric",

                });

                let mine = new Date().toLocaleTimeString('en-GB', {

                    minute: "numeric"
                });

                //ساعت جاری
                let timeToday = hour + ":" + mine


                //let selectTime = $("#loadingTime").val();  //ساعت انتخاب شده برای زمان بارگیری

                let selectTime = $("#loadingTime").val();  //ساعت انتخاب شده برای زمان بارگیری
                selectTime = selectTime.replace(/[\u0660-\u0669\u06F0-\u06F9]/g, d => string(d.charCodeAt(0) & 0xF));

                let checkDateB = selectedStr > toDayStr
                let checkDateK = selectedStr < toDayStr
                let checkDateM = selectedStr == toDayStr

                if (selectTime == "") {
                    setTimeout(() => {
                        toaster.toast('error', 'خطا', `لطفا زمان بارگیری را انتخاب نمایید!`);
                    }, 100);
                    return false;

                } else {

                    //چک کردن تاریخ روز جاری با روز تاریخ انتخاب شده برای کنترل زمان بارگیری
                    if (checkDateB === true) {

                        if (selectTime) {

                            setTimeout(x => {
                                $("#loadingTime").addClass("active");
                                $("#loadingTime").trigger("change");

                            }, 300)
                        }

                    }

                    else if (checkDateK === true) {
                        setTimeout(() => {
                            toaster.toast('error', 'خطا', `زمان بارگیری نمی تواند قبل از ساعت روز جاری باشد`);
                        }, 500);
                    }
                    else if (checkDateM === checkDateM) {
                        var currentTime = now.getHours() * 60 + now.getMinutes();

                        var parts = selectTime.split(':');
                        var SHours = parseInt(parts[0], 10);
                        var SMinutes = parseInt(parts[1], 10);
                        var SelectedTimeMinutes = SHours * 60 + SMinutes;

                        if (SelectedTimeMinutes >= currentTime) {
                            if (selectTime) {

                                setTimeout(x => {
                                    $("#loadingTime").addClass("active");
                                    $("#loadingTime").trigger("change");

                                }, 300)

                            }
                        }

                        else if (SelectedTimeMinutes < currentTime) {

                            setTimeout(() => {
                                toaster.toast('error', 'خطا', `زمان بارگیری نمی تواند قبل از ساعت روز جاری باشد`);
                            }, 500);
                            return $("#loadingTime").val("");
                        }
                        //else if (selectTime < timeToday) {
                        //    
                        //    setTimeout(() => {
                        //        toaster.toast('error', 'خطا', `زمان بارگیری نمی تواند قبل از ساعت روز جاری باشد`);
                        //    }, 500);
                        //    return $("#loadingTime").val("");
                        //}
                    }

                    return true;

                }


            }

        });

    })

    function validateTime() {

        var selectedDate = new Date();
        var now = new Date();

        var toDayStr = new persianDate().format('YYYY/MM/DD');
        toDayStr = toDayStr.replace(/[0-9]/g, d => '0123456789'.indexOf(d));
        var selectedStr = new persianDate(selectedDate).format('YYYY/MM/DD');

        //ساعت و دقیقه جاری
        let hour = new Date().toLocaleTimeString('en-GB', {
            hour: "numeric",

        });

        let mine = new Date().toLocaleTimeString('en-GB', {

            minute: "numeric"
        });

        //ساعت جاری
        let timeToday = hour + ":" + mine


        let selectTime = $("#loadingTime").val();  //ساعت انتخاب شده برای زمان بارگیری
        selectTime = selectTime.replace(/[\u0660-\u0669\u06F0-\u06F9]/g, d => string(d.charCodeAt(0) & 0xF));

        let checkDateB = selectedStr > toDayStr
        let checkDateK = selectedStr < toDayStr
        let checkDateM = selectedStr == toDayStr


        if (selectTime == "") {
            setTimeout(() => {
                toaster.toast('error', 'خطا', `لطفا زمان بارگیری را انتخاب نمایید!`);
            }, 100);
            return false;

        } else {

            //چک کردن تاریخ روز جاری با روز تاریخ انتخاب شده برای کنترل زمان بارگیری
            if (checkDateB === true) {

                if (selectTime) {

                    setTimeout(x => {
                        $("#loadingTime").addClass("active");
                        $("#loadingTime").trigger("change");

                    }, 300)
                }

            }

            else if (checkDateK === true) {
                setTimeout(() => {
                    toaster.toast('error', 'خطا', `زمان بارگیری نمی تواند قبل از ساعت روز جاری باشد`);
                }, 500);
            }
            else if (checkDateM === checkDateM) {
                if (selectTime >= timeToday) {
                    if (selectTime) {

                        setTimeout(x => {
                            $("#loadingTime").addClass("active");
                            $("#loadingTime").trigger("change");

                        }, 300)

                    }
                }
                else if (selectTime < timeToday) {
                    setTimeout(() => {
                        toaster.toast('error', 'خطا', `زمان بارگیری نمی تواند قبل از ساعت روز جاری باشد`);
                    }, 500);
                    return $("#loadingTime").val("");
                }
            }

            return true;

        }


    }

    //متد تایید ارسال یا عدم ارسال پیام به راننده پس از ثبت
    getShowSendNotify();
    function getShowSendNotify() {
        $('#loading').show();

        $.ajax({
            url: "/Barname/BondCarryingRosanne/GetCostSettings",
            type: "GET",
            data: {},
            success: function (result) {

                if (result != null) {

                    SendSMSShow = result.obj.senderSmsFlag;
                    if (SendSMSShow == true) {

                        $("#ShowSField").removeClass("hidden");
                    } else {

                        $("#ShowSField").addClass("hidden");
                    }



                } else {

                    toaster.toast('error', 'پیغام خطا', 'خطا در دریافت اطلاعات کاربر');
                }
            },
            Error: function (err) {
                $('#loading').hide();
                toaster.toast('error', 'پیغام خطا', 'خطایی رخ داده است لطفا با پشتیبانی تماس بگیرید');

            }
        });
    }

    //مراحل قبل و بعد برای هر ویزارد
    var objformhelper = new formHelper();
    $("#btnGoLVL2").on("click", function () {

        var SenderIDCard = $("#txtSenderNationalCode").val();
        if (!!SenderIDCard) {
            var IsSenderCompany = $("#senderSelectType").val()
            var SenderIDCardLenght = $("#txtSenderNationalCode").val().length;
            if (IsSenderCompany == 1 && SenderIDCardLenght !== 10) {
                toaster.toast('error', 'پیغام خطا', 'کد ملی شخص حقیقی 10 رقم است');
                return false;
            } else if (IsSenderCompany == 2 && SenderIDCardLenght !== 11) {
                toaster.toast('error', 'پیغام خطا', 'کد ملی شخص حقوقی 11 رقم است');
                return false;
            } else {
                objformhelper.init("frmSender");
                objformhelper.validate.init("frmSender")
                    .success(function () {
                        $("#GoLVL2").click()
                    })
                    .error(function (e) {
                        return false;
                    });
            }
        } else {
            objformhelper.init("frmSender");
            objformhelper.validate.init("frmSender")
                .success(function () {
                    $("#GoLVL2").click()
                })
                .error(function (e) {
                    return false;
                });
        }


    })
    $("#btnGoLVL3").on("click", function () {

        var ReceiverIDCard = $("#txtReceiverNationalCode").val();
        if (!!ReceiverIDCard) {
            var IsReceiverCompany = $("#receiverSelectType").val()
            var ReceiverIDCardLenght = $("#txtReceiverNationalCode").val().length;
            if (IsReceiverCompany == 1 && ReceiverIDCardLenght !== 10) {
                toaster.toast('error', 'پیغام خطا', 'کد ملی شخص حقیقی 10 رقم است');
                return false;
            } else if (IsReceiverCompany == 2 && ReceiverIDCardLenght !== 11) {
                toaster.toast('error', 'پیغام خطا', 'کد ملی شخص حقوقی 11 رقم است');
                return false;
            } else {
                objformhelper.init("frmReciver");
                objformhelper.validate.init("frmReciver")
                    .success(function () {
                        $("#GoLVL3").click()
                    })
                    .error(function (e) {
                        return false;
                    });
            }
        } else {
            objformhelper.init("frmReciver");
            objformhelper.validate.init("frmReciver")
                .success(function () {
                    $("#GoLVL3").click()
                })
                .error(function (e) {
                    return false;
                });
        }
    })
    $("#btnGoLVL4").on("click", function () {
        if (!CheckPelakInput()) {
            toaster.toast("error", "خطا", " لطفا شماره پلاک خود رو انتخاب کنید. ")
            return false;
        }
        if (GlobalTajmiiFlag) {
            if ($("#DriverListTajmi").val() == "") {
                toaster.toast("error", "خطا", " لطفا راننده مورد نظر خود را انتخاب کنید. ");
                return false;
            }


            objformhelper.init("frmDriverTajmi");
            objformhelper.validate.init("frmDriverTajmi")
                .success(function () {
                    $("#GoLVL4").click()
                })
                .error(function (e) {

                    return false;
                });
        }
        else {
            objformhelper.init("frmDriver");
            objformhelper.validate.init("frmDriver")
                .success(function () {
                    $("#GoLVL4").click()
                })
                .error(function (e) {
                    return false;
                });
        }

    })
    $("#btnGoLVL6").on("click", function () {

        var mapaddres = $("#txtAddressSourceFromMap").val();
        var SourcePost = $("#SourcePostalCodeFromMap").val();

        if (mapFlag == true) {
            $("#SourcePostalCode").val(SourcePost);
            $("#SourcePostalCodeView").val(SourcePost);
            if (!mapaddres) {

                toaster.toast('error', 'پیغام خطا', 'لطفا آدرس مبدا را از روی نقشه انتخاب نمایید');
                return false;
            }
            $("#GoStepMagsadBtn").click()
            showmapDest();
            //objformhelper.init("frmmabda");
            //objformhelper.validate.init("frmmabda")
            //    .success(function () {
            //    })
            //    .error(function (e) {
            //        return false;
            //    });

        } else {

            objformhelper.init("frmmabda");
            objformhelper.validate.init("frmmabda")
                .success(function () {
                    $("#GoStepMagsadBtn").click()

                })
                .error(function (e) {
                    return false;
                });
        }


    })
    $("#btnGoLVL7").on("click", function () {
        var mapaddres = $("#txtAddressDestFromMap").val();
        var DestPost = $("#destPostalCodeFromMap").val();
        var SourcePost = $("#SourcePostalCodeFromMap").val();

        if (mapFlag == true) {
            $("#destPostalCode").val(DestPost);
            $("#DestPostalCodeView").val(DestPost);
            $("#SourcePostalCodeView").val(SourcePost);
            if (!mapaddres) {

                toaster.toast('error', 'پیغام خطا', 'لطفا آدرس مقصد تخلیه را از روی نقشه انتخاب نمایید');
                return false;
            }
            $("#GoStepPreviewAddressBtn").click()
            //objformhelper.init("formmagsad");
            //objformhelper.validate.init("formmagsad")
            //    .success(function () {
            //    })
            //    .error(function (e) {
            //        return false;
            //    });


        } else {

            objformhelper.init("formmagsad");
            objformhelper.validate.init("formmagsad")
                .success(function () {
                    $("#GoStepPreviewAddressBtn").click()
                })
                .error(function (e) {
                    return false;
                });
        }
    })
    $("#btnGoLVL5").on("click", function () {

        objformhelper.init("frmBar");
        objformhelper.validate.init("frmBar")
            .success(function () {
                if (GlobalTajmiiFlag) {

                    //تبدیل به کیلوگرم
                    //var weightTon = totalWeight * 1000

                    //تبدیل به تن
                    if (CapaUnit == 1) {

                        var CapacityTajmiToTon = (CapacityTajmiTo / 1000).toFixed(1);

                    } else if (CapaUnit == 2) {
                        var CapacityTajmiToTon = CapacityTajmiTo;
                    } else if (CapaUnit == 3) {
                        var CapacityTajmiToTon = CapacityTajmiTo;
                    }

                    if (totalWeight > CapacityTajmiToTon) {

                        toaster.toast('error', 'پیغام خطا', ` حداکثر وزن بار مجاز شما ${CapacityTajmiToTon} تن است، اما مجموع وزن بار شما ${totalWeight} تن می باشد.`);
                        return false;
                    }
                }

                if (loadList.length > 0) {

                    $("#LoadNumberMinValidator").hide()
                    $("#GoLVL5").click();
                    setTimeout(x => {
                        showmapSource();

                    }, 400)
                }
                else {
                    $("#LoadNumberMinValidator").show()
                }


            })
            .error(function (e) {
                return false;
            });
    })
    //ثبت بارنامه مرحله و ویزارد آخر
    $("#btnregisterbarname").on("click", function () {
        IsDraft = false;
        objformhelper.init("frmkeraye");
        validateTime();
        objformhelper.validate.init("frmkeraye")
            .success(function () {
                $("#GoPil9").click()
            })
            .error(function (e) {
                return false;
            });
    })
    //ثبت پیش نویس ویزارد آخر
    $("#btndraft").on("click", function () {
        IsDraft = true;

        objformhelper.init("frmkeraye");
        objformhelper.validate.init("frmkeraye")
            .success(function () {
                $("#GoPil9").click()
            })
            .error(function (e) {
                return false;
            });
    })

    /*   if (true) {*/
    //بازگشت از علاقه مندی
    $("#frmPelakReturn").on("click", function () {
        $("#frmpelakFavorit").hide()
        $("#frmpelaq").show()
    })
    //radioButton نوع پلاک
    $("#azadPelakType").on("click", function () {

        $("#BoxSelect2").removeClass("active")
    })
    //ویزارد چهار 4 کمبوی جستجوی کالا
    $("#txtLoadName").autocomplete({
        source: function (request, response) {

            $.ajax({
                url: "/Barname/Document/KalaSearch",
                data: { txtkala: request.term },
                success: function (Doc) {
                    Doc = JSON.parse(Doc)
                    response(Doc);
                },
                error: function (error) {
                    $("#loading").hide();
                    return false;
                }
            });

        },
        minLength: 2,
        select: function (event, ui) {
            /*log("Selected: " + ui.item.value + " aka " + ui.item.id);*/
            $("#selecteditme").val(ui.item.id);
        }
    });


    InitSourceAddresses()
    InitDestAddresses()
    InitStepBtns()

    //به دلیل عدم استفاده کامنت شد #1
    //Disable Enter Key On Forms
    //$("#simplewizard-steps,#modal-Grid").keypress(function (e) {
    //    //Enter key
    //    if (e.which == 13) {
    //        return false;
    //    }
    //});

    $("#MSGBOXCity").hide();
    $("#pelakCombo1").val('');
    $("#azadPelakType1").hide();
    $("#detailsKAla").html('<div id="kala0" class="col-md-12 mt-2 row">' + DetailsHtml + '</div>');
    //$(window).load(function () { setTimeout(function () { $("#loading").hide() }, 1e3) });
    $("#chkInsurance").val("false");
    $("#frmSenderFavorit").hide();
    $("#frmReciverFavorit").hide();
    $("#ShowDetailsDriver").hide();
    $("#frmReciverFavorit").hide();
    $("#frmDriverFavorit").hide();
    $("#frmFavoritAddress").hide();
    $("#moshahedeKala").hide();
    $("#frmSenderAddressrFavorit").hide();
    $("#frmReciverAddressrFavorit").hide();
    $("#loading").hide();

    //کمبوی انتخاب شهر در بالای فرم نقشه ویزارد مبدا5
    $("#MapCity").select2("");
    $('#MapCity').select2();
    $('#MapCity').select2({
        placeholder: "شهرستان مورد نظر را انتخاب نمایید",
        allowClear: true,
        width: '100%',
        multiple: false,
        // minimumInputLength: 1,
        ajax: {
            url: "/Barname/Document/SearchMapCityListWithComboBox",
            dataType: 'json',
            delay: 1000,
            cache: true,
            type: "POST",
            //quietMillis: 50,
            data: function (term) {

                return {
                    term: term.term,
                    function: "SearchMapCityListWithComboBox"
                };
            },
            processResults: function (data, params) {

                return {
                    results: $.map(data, function (item) {
                        return {
                            text: item.mapCityName,
                            slug: item.mapCityName,
                            // id: item.Id
                            id: item.mapCityName
                        }
                    })
                };
            }
        },
        language: {
            noResults: function (params) {
                return "موردی یافت نشد.";
            },
            searching: function (params) {
                return "در حال جستجو...";
            },
            errorLoading: function (params) {
                return "موردی یافت نشد.";
            },

        }
    });
    // ویزارد مبدا 5 انتخاب کمبوی آدرس و جستجو در نقشه
    $("#AddressSearch").select2("");
    $('#AddressSearch').select2();
    $('#AddressSearch').select2({
        placeholder: "شهر/روستا/محله مورد نظر...",
        allowClear: true,
        width: '100%',
        multiple: false,

        ajax: {
            url: "/Barname/Document/SearchWithFilter",
            dataType: 'json',
            delay: 1000,
            //      cache: true,
            type: "POST",
            //quietMillis: 50,
            data: function (term) {

                return {
                    text: term.term,
                    filter: $('#MapCity').val(),
                    function: "SearchWithFilter"
                };
            },
            processResults: function (data, params) {
                return {
                    results: $.map((data).value, function (item) {

                        /*  results: $.map(JSON.parse(data).value, function (item) {*/
                        return {
                            text: item.title,
                            slug: item.title,
                            id: item.geom.coordinates[0] + "-" + item.geom.coordinates[1],

                        }
                    })
                };
            }
        },
        minimumInputLength: 3,
        language: {

            noResults: function (params) {

                return "موردی یافت نشد.";

            },
            inputTooShort: function (params) {
                return "لطفا حداقل 3 کاراکتر وارد کنید."
            },
            searching: function (params) {
                return "در حال جستجو...";
            },
            errorLoading: function (params) {
                return "موردی یافت نشد.";
            },

        },
        //language: 'fa',
    });


    //کمبوی انتخاب شهر در بالای فرم نقشه ویزارد مقصد6
    $("#MapCity2").select2("");
    $('#MapCity2').select2();
    $('#MapCity2').select2({
        placeholder: "شهرستان مورد نظر را انتخاب نمایید",
        allowClear: true,
        width: '100%',
        multiple: false,
        // minimumInputLength: 1,
        ajax: {
            url: "/Barname/Document/SearchMapCityListWithComboBox",
            dataType: 'json',
            delay: 1000,
            cache: true,
            type: "POST",
            //quietMillis: 50,
            data: function (term) {
                return {
                    term: term.term,
                    function: "SearchMapCityListWithComboBox"
                };
            },
            processResults: function (data, params) {
                return {
                    results: $.map(data, function (item) {
                        return {
                            text: item.mapCityName,
                            slug: item.mapCityName,
                            // id: item.Id
                            id: item.mapCityName
                        }
                    })
                };
            }
        },
        language: {
            noResults: function (params) {
                return "موردی یافت نشد.";
            },
            searching: function (params) {
                return "در حال جستجو...";
            },
            errorLoading: function (params) {
                return "موردی یافت نشد.";
            },


        }
    });
    // ویزارد مقصد 6 انتخاب کمبوی آدرس و جستجو در نقشه
    $("#AddressSearch2").select2("");
    $('#AddressSearch2').select2();
    $('#AddressSearch2').select2({
        placeholder: "شهر/روستا/محله مورد نظر...",
        allowClear: true,
        width: '100%',
        multiple: false,
        ajax: {
            url: "/Barname/Document/SearchWithFilter",
            dataType: 'json',
            delay: 1000,
            // cache: true,
            type: "POST",
            //quietMillis: 50,
            data: function (term) {
                return {
                    text: term.term,
                    filter: $('#MapCity').val(),
                    function: "SearchWithFilter"
                };
            },
            processResults: function (data, params) {
                return {

                    /* results: $.map(JSON.parse(data).value, function (item) {*/

                    results: $.map((data).value, function (item) {
                        return {
                            text: item.title,
                            slug: item.title,
                            id: item.geom.coordinates[0] + "-" + item.geom.coordinates[1],

                        }
                    })
                };
            }
        },
        multiple: false,
        minimumInputLength: 3,
        language: {

            noResults: function (params) {

                return "موردی یافت نشد.";

            },
            inputTooShort: function (params) {
                return "لطفا حداقل 3 کاراکتر وارد کنید."
            },
            searching: function (params) {
                return "در حال جستجو...";
            },
            errorLoading: function (params) {
                return "موردی یافت نشد.";
            },

        },
    })
    //}
    //else {
    //    return false;
    //}


    //نوع بارنامه حقیقی/ حقوقی برای ویزارد اول
    $("#senderSelectType").on("change", function () {


        var senderSelectTypeCom = $("#senderSelectType").val();

        if (senderSelectTypeCom == 2) {

            $("#SenderOfficeName").removeClass("hidden"); //نام شرکت
            //برای پاک کردن اجباری بودن فیلد نام
            $("#frmSender input[name='txtSenderFirstName']").removeAttr("required");
            $("#frmSender input[name='txtSenderFirstName']").removeAttr("data-fv-notempty-message");
            $("#frmSender input[name='txtSenderFirstName']").parents().parents().removeClass("has-success has-error");
            $("#frmSender").formValidation('removeField', $("#frmSender input[name='txtSenderFirstName']"));
            //برای پاک کردن اجباری بودن فیلد نام خانوادگی
            $("#frmSender input[name='txtSenderLastName']").removeAttr("required");
            $("#frmSender input[name='txtSenderLastName']").removeAttr("data-fv-notempty-message");
            $("#frmSender input[name='txtSenderLastName']").parents().parents().removeClass("has-success has-error");
            $("#frmSender").formValidation('removeField', $("#frmSender input[name='txtSenderLastName']"));
            //
            $("#senderName").addClass("hidden");
            $("#senderLastName").addClass("hidden");
            $("#txtSenderFirstName").val("");
            $("#txtSenderLastName").val("");
            $("#txtSenderMobile").val("");
            $("#txtSenderNationalCode").val("");
            $("#txtSenderTell").val("");
            $("#txtSenderPostalCode").val("");

        } else if (senderSelectTypeCom == 1) {
            $("#SenderOfficeName").addClass("hidden");
            $("#senderName").removeClass("hidden");
            $("#senderLastName").removeClass("hidden");
            //برای پاک کردن اجباری بودن فیلد نام شرکت
            $("#frmSender input[name='txtSenderOfficeName']").removeAttr("required");
            $("#frmSender input[name='txtSenderOfficeName']").removeAttr("data-fv-notempty-message");
            $("#frmSender input[name='txtSenderOfficeName']").parents().parents().removeClass("has-success has-error");
            $("#frmSender").formValidation('removeField', $("#frmSender input[name='txtSenderOfficeName']"));
            //
            $("#txtSenderOffice").val("");
            $("#txtSenderMobile").val("");
            $("#txtSenderNationalCode").val("");
            $("#txtSenderTell").val("");
            $("#txtSenderPostalCode").val("");
        }
        else {
            $("#SenderOfficeName").addClass("hidden");
            $("#senderName").addClass("hidden");
            $("#senderLastName").addClass("hidden");
        }

    });

    //نوع بارنامه حقیقی/ حقوقی برای ویزارد دوم
    $("#receiverSelectType").on("change", function () {

        var receiverSelectTypeCom = $("#receiverSelectType").val();


        if (receiverSelectTypeCom == 2) {
            $("#receiverOfficeName").removeClass("hidden"); //نام شرکت
            //برای پاک کردن اجباری بودن فیلد نام
            $("#frmReciver input[name='txtReceiverFirstName']").removeAttr("required");
            $("#frmReciver input[name='txtReceiverFirstName']").removeAttr("data-fv-notempty-message");
            $("#frmReciver input[name='txtReceiverFirstName']").parents().parents().removeClass("has-success has-error");
            $("#frmReciver").formValidation('removeField', $("#frmReciver input[name='txtReceiverFirstName']"));
            //برای پاک کردن اجباری بودن فیلد نام خانوادگی
            $("#frmReciver input[name='txtReceiverLastName']").removeAttr("required");
            $("#frmReciver input[name='txtReceiverLastName']").removeAttr("data-fv-notempty-message");
            $("#frmReciver input[name='txtReceiverLastName']").parents().parents().removeClass("has-success has-error");
            $("#frmReciver").formValidation('removeField', $("#frmReciver input[name='txtReceiverLastName']"));
            //
            $("#receiverName").addClass("hidden");
            $("#receiverLastName").addClass("hidden");
            $("#txtReceiverFirstName").val("");
            $("#txtreceiverLastName").val("");
            $("#txtReceiverMobile").val("");
            $("#txtReceiverNationalCode").val("");
            $("#txtReceiverTell").val("");
            $("#txtReceiverPostalCode").val("");


        } else if (receiverSelectTypeCom == 1) {
            $("#receiverOfficeName").addClass("hidden");
            $("#receiverName").removeClass("hidden");
            $("#receiverLastName").removeClass("hidden");
            $("#txtReceiverOfficeName").val("");
            //برای پاک کردن اجباری بودن فیلد نام  شرکت
            $("#frmReciver input[name='txtReceiverOfficeName']").removeAttr("required");
            $("#frmReciver input[name='txtReceiverOfficeName']").removeAttr("data-fv-notempty-message");
            $("#frmReciver input[name='txtReceiverOfficeName']").parents().parents().removeClass("has-success has-error");
            $("#frmReciver").formValidation('removeField', $("#frmReciver input[name='txtReceiverOfficeName']"));
            //
            $("#txtReceiverMobile").val("");
            $("#txtReceiverNationalCode").val("");
            $("#txtReceiverTell").val("");
            $("#txtReceiverPostalCode").val("");

        }
        else {

            $("#ReceiverOfficeName").addClass("hidden");
            $("#receiverName").addClass("hidden");
            $("#receiverLastName").addClass("hidden");
        }




    });

    $("#BackPill8").on("click", function () {
        $("#pills-tab").removeClass("d-none");
    });
});

//اعتبارسنجی پلاک در صورتی که تجمیع فعال نیست
function CheckPelakInput() {

    if (!GlobalTajmiiFlag) {

        if ($("[name='pelakIsAzad']:checked").val() == "2") {
            if ($("#pelakFirst").val() == "" || $("#pelakIrNum").val() == "" || $("#pelakCenter").val() == "" || $("#pelakCombo").val() == "") {
                $("#pelakinvalidtotal").show()
                return false;
            }
            else {
                $("#pelakinvalidtotal").hide()
                return true;
            }
        }
        else {
            if ($("#pelakTypeCombo").val() == "" || $("#pelakAzadFarsiNumber").val() == "") {
                $("#pelakinvalidtotal").show()
                return false;
            }
            else {
                $("#pelakinvalidtotal").hide()
                return true;
            }
        }
    }
    else {

        if ($("#PelakComboTajmi").val() != "") {
            return true;
        }
        else {
            return false;
        }
    }

}

function InitStepBtns() {
    //مرحله بعدی ویزارد پنجم
    $("#GoStepMagsadBtn").on("click", function () {
        $("#txtAddressSourceView").val($("#txtAddressSource").val())
        $("#SourcePostalCodeView").val($("#sourcePostalCode").val())

    })
    //مرحله قبلی ویزارد پنجم
    $("#GoStepPreviewAddressBtn").on("click", function () {
        $("#txtAddressDestView").val($("#txtAddressDest").val())
        $("#destPostalCodeView").val($("#destPostalCode").val())

    })
}
//کمبوی استان و شهر در صورتی که نقشه غیرفعال باشد ویزارد مبدا بارگیری
function InitSourceAddresses() {
    $.ajax({
        url: "/Barname/Document/FillProvinces",
        data: { /*txtkala: selectedValue */ },
        success: function (res) {
            res = JSON.parse(res)
            $("#loading").hide();
            if (res.resultCode == 0 || res.resultCode == 200) {
                let Doc = res.obj


                $("#ddStateSource").empty();
                var ddStateSource = $("#ddStateSource");
                ddStateSource.append("<option value=''>انتخاب کنید</option>");
                $.each(Doc, function () {
                    ddStateSource.append("<option value=" + this.id + ">" + this.name + "</option>");
                });

            }
            else {
                toaster.toast("error", "خطا", res.resultMessage)
            }

        },
        error: function (error) {
            $("#loading").hide();
            toaster.toast("error", "خطا", error)
        }
    })

    $("#ddStateSource").on("change", function () {
        $.ajax({
            url: "/Barname/Document/FillCities",
            data: {
                StateId: $("#ddStateSource").val()
            },
            success: function (res) {
                res = JSON.parse(res)
                $("#loading").hide();
                if (res.resultCode == 0 || res.resultCode == 200) {
                    let Doc = res.obj


                    $("#ddCitySource").empty();
                    var ddCitySource = $("#ddCitySource");
                    ddCitySource.append("<option value=''>انتخاب کنید</option>");
                    $.each(Doc, function () {
                        ddCitySource.append("<option value=" + this.id + ">" + this.name + "</option>");
                    });
                    if (ddCitySourceId != 0) { $("#ddCitySource").val(ddCitySourceId); ddCitySourceId = 0; }

                }
                else {
                    toaster.toast("error", "خطا", res.resultMessage)
                }

            },
            error: function (error) {
                $("#loading").hide();
                toaster.toast("error", "خطا", error)
            }
        })
    })
}
//کمبوی استان و شهر در صورتی که نقشه غیرفعال باشد ویزارد مقصد تخلیه
function InitDestAddresses() {
    $.ajax({
        url: "/Barname/Document/FillProvinces",
        data: { /*txtkala: selectedValue */ },
        success: function (res) {
            res = JSON.parse(res)
            $("#loading").hide();
            if (res.resultCode == 0 || res.resultCode == 200) {
                let Doc = res.obj


                $("#ddStateDest").empty();
                var ddStateDest = $("#ddStateDest");
                ddStateDest.append("<option value=''>انتخاب کنید</option>");
                $.each(Doc, function () {
                    ddStateDest.append("<option value=" + this.id + ">" + this.name + "</option>");
                });
            }
            else {
                toaster.toast("error", "خطا", res.resultMessage)
            }

        },
        error: function (error) {
            $("#loading").hide();
            toaster.toast("error", "خطا", error)
        }
    })

    $("#ddStateDest").on("change", function () {
        $.ajax({
            url: "/Barname/Document/FillCities",
            data: {
                StateId: $("#ddStateDest").val()
            },
            success: function (res) {
                res = JSON.parse(res)
                $("#loading").hide();
                if (res.resultCode == 0 || res.resultCode == 200) {
                    let Doc = res.obj


                    $("#ddCityDest").empty();
                    var ddCityDest = $("#ddCityDest");
                    ddCityDest.append("<option value=''>انتخاب کنید</option>");
                    $.each(Doc, function () {
                        ddCityDest.append("<option value=" + this.id + ">" + this.name + "</option>");
                    });
                    if (ddCityDestId != 0) {
                        $("#ddCityDest").val(ddCityDestId).trigger("change");
                        ddCityDestId = 0;
                    }
                }
                else {
                    toaster.toast("error", "خطا", res.resultMessage)
                }

            },
            error: function (error) {
                $("#loading").hide();
                toaster.toast("error", "خطا", error)
            }
        })
    })
}

var FormDocumenDetailsRegister = function () {
    var objformhelper = new formHelper();
    var initializing = function () {
        return {
            init: function () {
                initializing.initfrmSender();
                initializing.initfrmReciver();
                initializing.initfrmDriverAndCar();
                initializing.initfrmcommodity();

                initializing.initfrmmabda();
                initializing.initfrmmabdaMapFlage();
                initializing.initformmagsad();
                initializing.initformmagsadMapFlage();

                initializing.initfrmLoadingAndUnloadingOrigin();
                initializing.initfrmLoadingAndUnloadingOriginMapFlage();
                initializing.initfrmLoadingAndUnloadingDestination();
                initializing.initfrmLoadingAndUnloadingDestinationMapFlage();
                initializing.initfrmFare();
                initializing.initfrmmodalsender();
                initializing.initfrmmodalreceiver();
                initializing.initfrmDriver();
                initializing.initfrmpelaq();
                initializing.initfrmAddressModal();
                initializing.initfrmLoadModal();
                initializing.initfrmcommodityInsert();

                /* initializing.initfrmCaptcha();*/
            },

            initfrmSender: function () {
                objformhelper.init("frmSender");
            },

            initfrmReciver: function () {
                objformhelper.init("frmReciver");
            },
            initfrmDriverAndCar: function () {
                //objformhelper.init("frmDriverAndCar");
            },
            initfrmcommodity: function () {
                objformhelper.init("frmcommodity");
            },

            initfrmmabda: function () {
                objformhelper.init("frmmabda");
            },
            initfrmmabdaMapFlage: function () {
                //objformhelper.init("frmmabdaMapFlage");
            },
            initformmagsad: function () {
                objformhelper.init("formmagsad");
            },
            initformmagsadMapFlage: function () {
                /* objformhelper.init("formmagsadMapFlage");*/
            },

            initfrmLoadingAndUnloadingOrigin: function () {
                //objformhelper.init("frmLoadingAndUnloadingOrigin");
            },
            initfrmLoadingAndUnloadingOriginMapFlage: function () {
                //objformhelper.init("frmLoadingAndUnloadingOriginMapFlage");
            },
            initfrmLoadingAndUnloadingDestination: function () {
                //objformhelper.init("frmLoadingAndUnloadingDestination");
            },
            initfrmLoadingAndUnloadingDestinationMapFlage: function () {
                objformhelper.init("frmLoadingAndUnloadingDestinationMapFlage");
            },
            initfrmFare: function () {
                //objformhelper.init("frmFare");
            },
            initfrmmodalsender: function () {
                //objformhelper.init("frmmodalsender");
            },
            initfrmmodalreceiver: function () {
                //objformhelper.init("frmmodalreceiver");
            },
            initfrmDriver: function () {
                objformhelper.init("frmDriver");
            },
            initfrmpelaq: function () {
                objformhelper.init("frmpelaq");
            },
            initfrmAddressModal: function () {
                //objformhelper.init("frmAddressModal");
            },
            initfrmLoadModal: function () {
                //objformhelper.init("frmcommodityModal");
            },
            initfrmcommodityInsert: function () {
                objformhelper.init("frmcommodityInsert");
            },
            initfrmCaptcha: function () {
                // objformhelper.init("frmCaptcha");
            },
        }
    }();
    var binding = function () {
        return {
            bindingevent: function () {
                binding.bindFormShippingDocumentationSystem();

            },
            bindFormShippingDocumentationSystem: function () {
                $("#btnsearchAddressSource").on("click", function () {
                    if ($('#AddressSearch').val() != null && $('#AddressSearch').val() != "") {
                        var Coordinates = $('#AddressSearch').val().split("-");
                        if (appMap != null) {
                            var crosshairIcon = {
                                iconUrl: 'https://cdn.map.ir/web-sdk/1.4.2/assets/images/icongreen.png',
                                iconSize: [37, 37], // size of the icon
                                iconAnchor: [37, 37], // point of the icon which will correspond to marker's location
                            };
                            //var marker = appMap.addMarker({
                            //    name: 'advanced-marker',
                            //    latlng: {
                            //        lat: Coordinates[1],
                            //        lng: Coordinates[0]
                            //    },
                            //    zoom: 22,
                            //    icon: crosshairIcon,
                            //    popup: false
                            //});
                            appMap.map.setView([Coordinates[1], Coordinates[0]], 15);
                            appMap.map.fire('click', {
                                latlng: {
                                    lat: Coordinates[1],
                                    lng: Coordinates[0],
                                },
                            });
                        }
                    }
                    else {
                        toaster.toast("error", "هشدار ", "لطفا ابتدا شهر و آدرس مورد نظر را جستجو و انتخاب نمایید")

                    }
                });
                $('#AddressSearch').on("change", function () {

                    if ($('#AddressSearch').val() != null && $('#AddressSearch').val() != "") {
                        var Coordinates = $('#AddressSearch').val().split("-");
                        if (appMap != null) {
                            var crosshairIcon = {
                                iconUrl: '../Scripts/MainScript/MapFile/assets/images/iconblue.png',
                                iconSize: [37, 37], // size of the icon
                                iconAnchor: [37, 37], // point of the icon which will correspond to marker's location
                            };
                            //var marker = appMap.addMarker({
                            //    name: 'advanced-marker',
                            //    latlng: {
                            //        lat: Coordinates[1],
                            //        lng: Coordinates[0]
                            //    },
                            //    zoom: 22,
                            //    icon: crosshairIcon,
                            //    popup: false
                            //});
                            appMap.map.setView([Coordinates[1], Coordinates[0]], 15);
                            appMap.map.fire('click', {
                                latlng: {
                                    lat: Coordinates[1],
                                    lng: Coordinates[0],
                                },
                            });
                        }
                    }

                });
                $("#btnsearchAddressDes").on("click", function () {

                    if ($('#AddressSearch2').val() != null && $('#AddressSearch2').val() != "") {
                        var Coordinates = $('#AddressSearch2').val().split("-");
                        if (appMap2 != null) {
                            var crosshairIcon = {
                                iconUrl: 'https://cdn.map.ir/web-sdk/1.4.2/assets/images/icon.png',
                                iconSize: [37, 37], // size of the icon
                                iconAnchor: [37, 37], // point of the icon which will correspond to marker's location
                            };
                            //appMap2.addMarker({
                            //    name: 'advanced-marker',
                            //    latlng: {
                            //        lat: Coordinates[1],
                            //        lng: Coordinates[0]
                            //    },
                            //    zoom: 22,
                            //    icon: crosshairIcon,
                            //    popup: false
                            //});
                            //appMap.map.panTo(new L.LatLng(Coordinates[1], Coordinates[0]));
                            appMap2.map.setView([Coordinates[1], Coordinates[0]], 15);
                            appMap2.map.fire('click', {
                                latlng: {
                                    lat: Coordinates[1],
                                    lng: Coordinates[0],
                                },
                            });
                        }
                    }
                    else {
                        toaster.toast("error", " هشدار", "لطفا ابتدا شهر و آدرس مورد نظر را جستجو و انتخاب نمایید")

                    }
                });
                $('#AddressSearch2').on("change", function () {

                    if ($('#AddressSearch2').val() != null && $('#AddressSearch2').val() != "") {
                        var Coordinates = $('#AddressSearch2').val().split("-");
                        if (appMap2 != null) {
                            var crosshairIcon = {
                                iconUrl: '../Scripts/MainScript/MapFile/assets/images/icon.png',
                                iconSize: [37, 37], // size of the icon
                                iconAnchor: [37, 37], // point of the icon which will correspond to marker's location
                            };
                            //appMap2.addMarker({
                            //    name: 'advanced-marker',
                            //    latlng: {
                            //        lat: Coordinates[1],
                            //        lng: Coordinates[0]
                            //    },
                            //    zoom: 3,
                            //    icon: crosshairIcon,
                            //    popup: false
                            //});
                            //appMap.map.panTo(new L.LatLng(Coordinates[1], Coordinates[0]));
                            appMap2.map.setView([Coordinates[1], Coordinates[0]], 15);
                            appMap2.map.fire('click', {
                                latlng: {
                                    lat: Coordinates[1],
                                    lng: Coordinates[0],
                                },
                            });
                        }
                    }

                });
                setTimeout(function () {
                    $('div .mm-dropdown > ul > li').on("click", FormShippingDocumentationSystemClick.changeComboPelakClick);
                }, 5000);
                $("#DriverListTajmi").on("change", FormShippingDocumentationSystemClick.changeComboDriverClick);
                /////-----------------------------------sender
                $("#btnSenderReturn").on("click", FormShippingDocumentationSystemClick.SenderReturn);

                $("#btnSenderNext").on("click", FormShippingDocumentationSystemClick.functionSender);

                $("#ddSender").on("change", FormShippingDocumentationSystemClick.SelectedSender);
                $("#btnRegPreSender").on("click", FormShippingDocumentationSystemClick.btnRegPreSender);

                $("#senderfavorite").on("click", FormShippingDocumentationSystemClick.showgrideSender);
                $("#gridfullsender").on("draw.dt", function () {
                    $("[name='selectSender']").on("click", FormShippingDocumentationSystemClick.selectSender);
                    $("[name='editSender']").on("click", FormShippingDocumentationSystemClick.btneditDeatailSender);
                    $("[name='deleteSender']").on("click", FormShippingDocumentationSystemClick.btnDeleteDetailsSender);
                });
                $("#btnUpdatePreSenderModal").on("click", FormShippingDocumentationSystemClick.UpdateSender);
                $("#frmSenderReturn").on("click", FormShippingDocumentationSystemClick.SendergridReturn);
                $("#frmPelakReturn").on("click", FormShippingDocumentationSystemClick.SendBackForm);
                $("#Sendersearch").on("click", function () {
                    myDataTable.ajax.reload();
                });
                ////----------------------------------------reciver
                $("#btnReciverReturn").on("click", FormShippingDocumentationSystemClick.ReciverReturn);
                $("#btnReciverNext").on("click", FormShippingDocumentationSystemClick.ReciverNext);
                $("#ddReceiver").on("change", FormShippingDocumentationSystemClick.SelectedReceiver);
                $("#reciverfavorite").on("click", FormShippingDocumentationSystemClick.reciverfavorite);
                //-----علاقه مندی ادرس مبدا/مقصد
                $("#senderAddressfavorite").on("click", FormShippingDocumentationSystemClick.AddressSenderfavorite);
                /*  $("#frmSenderAddressReturn").on("click", FormShippingDocumentationSystemClick.addresSenderdReturn);*/
                $("#reciverAddressfavorite").on("click", FormShippingDocumentationSystemClick.AddressReciverfavorite);
                /* $("#frmReciverAddressReturn").on("click", FormShippingDocumentationSystemClick.addressReciverReturn);*/
                $("#frmSenderAddressrFavoritReturn").on("click", FormShippingDocumentationSystemClick.addresSenderdReturn);
                $("#frmReceiverAddressrFavoritReturn").on("click", FormShippingDocumentationSystemClick.addressReciverReturn);
                //---عملیات حذف/ انتخاب
                $("#gridfulSenderAddress").on("draw.dt", function () {
                    $("[name='selectSenderAddress']").on("click", FormShippingDocumentationSystemClick.selectSenderAddress);
                    $("[name='deleteSenderAddress']").on("click", FormShippingDocumentationSystemClick.DeleteSenderAddress);
                });

                $("#gridfulReciverAddress").on("draw.dt", function () {
                    $("[name='selectReciverAddress']").on("click", FormShippingDocumentationSystemClick.selectReceiverAddress);
                    $("[name='deleteReciverAddress']").on("click", FormShippingDocumentationSystemClick.DeleteReceiverAddress);
                });
                //--افزودن به علاقه مندی ادرس مبدا / مقصد
                $("#btnRegPreSenderAddress").on("click", FormShippingDocumentationSystemClick.btnRegPreSenderAddress);
                $("#btnRegPreReceiverAddress").on("click", FormShippingDocumentationSystemClick.btnRegPreReceiverAddress);
                //-----------------------------

                $("#gridfullreceiver").on("draw.dt", function () {
                    $("[name='selectReceiver']").on("click", FormShippingDocumentationSystemClick.selectReceiver);
                    $("[name='editReciver']").on("click", FormShippingDocumentationSystemClick.btneditDeatailReceiver);
                    $("[name='deleteReciver']").on("click", FormShippingDocumentationSystemClick.btnDeleteDetailsReceiver);
                });
                $("#btnUpdatePreReceiverModal").on("click", FormShippingDocumentationSystemClick.UpdateReceiver);
                $("#btnRegPreReceiver").on("click", FormShippingDocumentationSystemClick.btnRegPreReceiver);
                $("#frmreciverReturn").on("click", FormShippingDocumentationSystemClick.receivergridReturn);
                $("#receiversearch").on("click", function () {
                    myDataTableReceiver.ajax.reload();
                });
                ///-------------------------------------------Driver-------------------------------------
                /*$("#btnShowDetailsDriver").on("click", FormShippingDocumentationSystemClick.DriverSearch);*/
                $("#driversearch").on("click", function () {
                    myDataTableDriver.ajax.reload();
                });
                $("#gridfulldriver").on("draw.dt", function () {
                    $("[name='selectDriver']").on("click", FormShippingDocumentationSystemClick.selectDriver);
                    $("[name='deleteDriver']").on("click", FormShippingDocumentationSystemClick.btnDeleteDetailsDriver);
                });
                $("#btnDriverFavorit").on("click", FormShippingDocumentationSystemClick.btnDriverFavorit);
                $("#btnRegDriver").on("click", FormShippingDocumentationSystemClick.btnRegDriver);
                $("#frmDriverReturn").on("click", FormShippingDocumentationSystemClick.drivergridReturn);
                //---------------------------------------------pelaq-----------------------------------
                $("#frmpelaq input[name='pelakIsAzad']").on("click", FormShippingDocumentationSystemClick.getPelakType);
                $("#frmpelaq select[name='pelakTypeCombo']").on("change", FormShippingDocumentationSystemClick.changePelakAzadCombo);
                $("#frmpelaq input[name='pelakAzadFarsiNumber']").on("input", function (e) {
                    $("#frmpelaq input[name='pelakAzadLatinNumber']").val($(this).val()).trigger("change");
                });
                $("#frmpelaq input[name='pelakAzadLatinNumber']").on("input", function (e) {
                    $("#frmpelaq input[name='pelakAzadFarsiNumber']").val($(this).val()).trigger("change");
                });
                $("#frmpelaq input[name='pelakIrNum']").on("input", FormShippingDocumentationSystemClick.checkPelakRequired);
                $("#frmpelaq input[name='pelakCenter']").on("input", FormShippingDocumentationSystemClick.checkPelakRequired);
                $("#frmpelaq input[name='pelakFirst']").on("input", FormShippingDocumentationSystemClick.checkPelakRequired);
                $("#frmpelaq select[name='pelakCombo']").on("change", FormShippingDocumentationSystemClick.checkPelakRequired);

                $("#frmpelaqTajmi select[name='PelakComboTajmi']").on("change", FormShippingDocumentationSystemClick.changeComboPelaktajmi);

                $("#BtnRefreshPelaq").on("click", FormShippingDocumentationSystemClick.RefreshFleetListTajmi);


                //-------------------------------------------Kala----------------------------------------------------

                $("#ddKala").on("change", FormShippingDocumentationSystemClick.SelectedKala);
                $("#btnRegPreKala").on("click", FormShippingDocumentationSystemClick.btnRegPreKala);

                //$("#kalafavorite").on("click", FormShippingDocumentationSystemClick.showgrideKala);
                $("#gridfullKala").on("draw.dt", function () {
                    $("[name='selectKala']").on("click", FormShippingDocumentationSystemClick.btnAddSelectedKala);
                    $("[name='editKala']").on("click", FormShippingDocumentationSystemClick.btneditDeatailKala);
                    $("[name='deleteKala']").on("click", FormShippingDocumentationSystemClick.btnDeleteDetailsKala);
                });
                //باتن جستجو از لیست علاقه مندی های کالا
                $("#PreKalasearch").on("click", function () {
                    myDataTableKala.ajax.reload();
                });

                $("#frmKalaReturn").on("click", FormShippingDocumentationSystemClick.KalagridReturn);


                //-----sendSms--------------

                $("#sendsmsvalue").on("change", FormShippingDocumentationSystemClick.sendsmsvalue);

                $("#pelakTypeNormal").click(function () {
                    var test = $(this).val();

                    $("#azadPelakType1").hide();

                    $("#frmpelaq input[name='pelakType']:checked").val(2);
                    $("#AdiColor").css("color", "#fffff");
                    $("#AdiBackground").css("background-color", "#3bacff");
                    $("#AzadColor").css("color", "#007e90");
                    $("#AzadBackground").css("background-color", "#fffff");

                    $("#pelakAzadFarsiNumber1").val("");
                    $("#pelakTypeCombo1").val("");
                    $("#pelakAzadLatinNumber1").val("");

                    $("#azadPelakType2").show();
                });
                $("#pelakTypeFreeZone").click(function () {


                    $("#azadPelakType2").hide();

                    $("#frmpelaq input[name='pelakType']:checked").val(1);
                    $("#AzadColor").css("color", "#fffff");
                    $("#AzadBackground").css("background-color", "#3bacff");
                    $("#AdiColor").css("color", "#007e90");
                    $("#AdiBackground").css("background-color", "#fffff");
                    $("#pelakIrNum1").val("");
                    $("#pelakCenter1").val("");
                    $("#pelakCombo1").val("");
                    $("#pelakFirst1").val("");
                    $("#azadPelakType1").show();


                });

                /*$("#btnShowDetailsDriver").on("click", FormShippingDocumentationSystemClick.DriverSearch);*/
                $("#btndriverCarReturn").on("click", FormShippingDocumentationSystemClick.DriverCarReturn);
                $("#btnDriverCarNext").on("click", FormShippingDocumentationSystemClick.DriverCarNext);
                /* $("#btnShowDetailspelaq").on("click", FormShippingDocumentationSystemClick.PlaqueSearch);*/
                $("#btnPelaqFavorit").on("click", FormShippingDocumentationSystemClick.btnPelaqFavorit);
                $("#gridfullPelak").on("draw.dt", function () {
                    $("[name='selectPelak']").on("click", FormShippingDocumentationSystemClick.selectPelak);
                    $("[name='deletePelak']").on("click", FormShippingDocumentationSystemClick.btnDeletePelak);
                });
                $("#btnRegPelak").on("click", FormShippingDocumentationSystemClick.btnRegPelak);

                //--------------------------------------------frmcommodity---------------------------
                $("#btnAddLoad").on("click", FormShippingDocumentationSystemClick.btnAddLoad);
                $("#kalafavorite").on("click", FormShippingDocumentationSystemClick.btnkalafavorite);
                $("#txtLoadName").on("change", function () {
                    $("#txtLoadNameValidationSpan").hide()
                    FormShippingDocumentationSystemClick.validationLoadChange();
                });





                $("#btnInsertLoad").on("click", FormShippingDocumentationSystemClick.validationLoad);
                $("#btncommodityRreturn").on("click", FormShippingDocumentationSystemClick.commodityRreturn);
                $("#btncommodityNext").on("click", FormShippingDocumentationSystemClick.commodityNextCount);
                $("input[name='chkInsurance']").on("click", FormShippingDocumentationSystemClick.commoditycheckbox);
                $("input[name='txtLoadsValue']").keyup(FormShippingDocumentationSystemClick.setcama);


                $("#pelas").on("click", function () {
                    var incrament = parseInt($("#txtBoxNum").val());
                    pelas++;
                    $("#txtBoxNum").val(pelas).trigger("change");
                });
                $("#mainez").on("click", function () {
                    if ($("#txtBoxNum").val() >= '1') {

                        var incrament = parseInt($("#txtBoxNum").val());
                        pelas--;
                        $("#txtBoxNum").val(pelas).trigger("change");
                    }
                });
                $("#pelasModal").on("click", function () {
                    var incrament = parseInt($("#txtBoxNumModal").val());
                    pelasModal++;
                    $("#txtBoxNumModal").val(pelasModal)
                });
                $("#mainezModal").on("click", function () {
                    if ($("#txtBoxNumModal").val() >= '1') {

                        var incrament = parseInt($("#txtBoxNumModal").val());
                        pelasModal--;
                        $("#txtBoxNumModal").val(pelasModal)
                    }
                });


                $("#LoadShow").on("click", FormShippingDocumentationSystemClick.LoadShow);
                $("#txtkala2").on("change", FormShippingDocumentationSystemClick.kalaSearchModal);
                $("#btnUpdateLoadModal").on("click", FormShippingDocumentationSystemClick.btnUpdateModal);
                //--------------------------------------------LoadingAndUnloadingOrigin
                //$("#ddStateSource").on("change", FormShippingDocumentationSystemClick.GetCitiesSource);
                $("#OrginState").on("change", FormShippingDocumentationSystemClick.GetCitiesSource);
                $("#DestinationState").on("change", FormShippingDocumentationSystemClick.GetCitiesDestination);
                $("#PreSource").on("change", FormShippingDocumentationSystemClick.SelectedAddressSource);
                $("#PreAddressFavoritOrigin").on("click", FormShippingDocumentationSystemClick.PreAddressFavoritOrigin);
                //  $("#ddState").on("change", FormShippingDocumentationSystemClick.GetCitiesAddress);
                $("#gridfullOrigin").on("draw.dt", function () {
                    $("[name='selectAddressOrigin']").on("click", FormShippingDocumentationSystemClick.selectAddressOrigin);
                    $("[name='editAddressOrigin']").on("click", FormShippingDocumentationSystemClick.btnDetailseditPreAddressOrigin);
                    $("[name='deleteAddressOrigin']").on("click", FormShippingDocumentationSystemClick.deleteAddressOrigin);
                });
                $("#Originsearch").on("click", FormShippingDocumentationSystemClick.Originsearch);
                $("#frmFavoritAddressReturnOrigin").on("click", FormShippingDocumentationSystemClick.frmFavoritAddressReturnOrigin);
                //-------------------LoadingAndUnloadingOriginLoadingAndUnloadingDestination
                $("#btnUpdatePreAddressModal").on("click", FormShippingDocumentationSystemClick.editAddressOrigin);
                //-----------------------------------------------------------------------------------
                $("#PreAddressInsertOrigin").on("click", FormShippingDocumentationSystemClick.PreAddressInsertOrigin);
                $("[name='btnLoadingAndUnloadingOriginReturn']").on("click", FormShippingDocumentationSystemClick.LoadingAndUnloadingOriginReturn);
                $("[name='btnLoadingAndUnloadingOriginNext']").on("click", FormShippingDocumentationSystemClick.LoadingAndUnloadingOriginNext);
                //--------------------------------------------LoadingAndUnloadingDestination
                // $("#ddStateDest").on("change", FormShippingDocumentationSystemClick.GetCitiesDest);
                $("#PreDest").on("change", FormShippingDocumentationSystemClick.SelectedAddressDest);
                $("#PreAddressFavoritdestination").on("click", FormShippingDocumentationSystemClick.PreAddressFavoritdestination);
                $("#gridfullDest").on("draw.dt", function () {
                    $("[name='selectAddressDest']").on("click", FormShippingDocumentationSystemClick.selectAddressDest);
                    $("[name='editAddressDest']").on("click", FormShippingDocumentationSystemClick.btnDetailseditPreAddressDest);
                    $("[name='deleteAddressDest']").on("click", FormShippingDocumentationSystemClick.deleteAddressDest);
                });
                $("#Destsearch").on("click", FormShippingDocumentationSystemClick.Destsearch);
                $("#frmFavoritAddressReturnDest").on("click", FormShippingDocumentationSystemClick.frmFavoritAddressReturnDest);
                //$("#PreAddressInsertdestination").on("click", FormShippingDocumentationSystemClick.PreAddressInsertDest);
                $("[name='btnLoadingAndUnloadingDestinationReturn']").on("click", FormShippingDocumentationSystemClick.LoadingAndUnloadingDestinationReturn);
                $("[name='btnLoadingAndUnloadingDestinationNext']").on("click", FormShippingDocumentationSystemClick.LoadingAndUnloadingDestinationNext);

                $("#btnBackDestination").on("click", FormShippingDocumentationSystemClick.btnBackDestination);

                $("#btnNextPriveiwInfo").on("click", FormShippingDocumentationSystemClick.btnNextPriveiwInfo);



                $("[name='btnRouteMapNext']").on("click", FormShippingDocumentationSystemClick.LoadingRouteMapNext);

                $("#btnFareReturn").on("click", FormShippingDocumentationSystemClick.FareReturn);
                //-----------------------------------------------Fare
                $("#btnRegister").on("click", FormShippingDocumentationSystemClick.btnRegister);
                $("#GoPil9").on("click", FormShippingDocumentationSystemClick.btnRegister);
                $("#txtkeraye").on("change", FormShippingDocumentationSystemClick.resultKeraye);
                $("input[id='txtkeraye']").keyup(function () {

                    $("#txtkeraye").val(generalCls.Comma($("#txtkeraye").val()));
                });
                $("input[id='txtPishKeraye']").keyup(function () {

                    $("#txtPishKeraye").val(generalCls.Comma($("#txtPishKeraye").val()));
                });
                $("#txtPishKeraye").on("change", FormShippingDocumentationSystemClick.resultKeraye);
                //---------------------------------------------Details
                $("#btnRegisterFinishedReturn").on("click", FormShippingDocumentationSystemClick.btnRegisterFinishedReturn);
                $("#btnTempRegister").on("click", FormShippingDocumentationSystemClick.btnTempRegister);
                $("#btnRegisterFinished").on("click", FormShippingDocumentationSystemClick.btnRegisterFinished);
                //----------------------
                $("#frmLoadFavoritReturn").on("click", FormShippingDocumentationSystemClick.backToWizardKala);
                $("#NewRegister").on("click", FormShippingDocumentationSystemClick.NewRegister);
                $("#printb").on("click", FormShippingDocumentationSystemClick.printbarbarg);
                $("#btnPrintSender").on("click", FormShippingDocumentationSystemClick.PrintSender);
                $("#btnPrintReceiver").on("click", FormShippingDocumentationSystemClick.PrintReceiver);
                $("#btnPrintDriver").on("click", FormShippingDocumentationSystemClick.PrintDriver);



            },
            bindEditBtns: function () {
                $("button[name=editLoadBtn]").on("click", function (e) {
                    var ItemID = $(this).attr("ID");
                    FormShippingDocumentationSystemClick.UpdateLoadModal(ItemID);
                });
            },
            bindSelectedBtns: function () {
                $("button[name=selectLoad]").on("click", function (e) {
                    var ItemID = $(this).attr("ID");
                    FormShippingDocumentationSystemClick.selectLoad(ItemID);
                });
            },
            binddeleteLoadBtns: function () {
                $("button[name=deleteLoad]").on("click", function (e) {
                    var ItemID = $(this).attr("ID");
                    FormShippingDocumentationSystemClick.btnDeleteLoad(ItemID);
                });
            },
        }
    }();
    var generalCls = function () {
        return {
            SetWizard: function (a) {
                var x = a;
                //myAdded
                for (var i = 0; i <= 10; i++) {
                    $("#s" + i).removeClass("complete");
                    $("#s" + i).removeClass("active");
                    $("#s" + i).addClass("step-pane");
                    $('#simplewizardstep' + (i)).attr("class", "step-pane");
                }
                //end Added
                $("#s" + (x + 1)).removeClass("active");

                for (var i = 0; i <= x; i++) {
                    $("#s" + i).attr("class", "complete");
                }
                $("#s" + x).attr("class", "active");
                $('#simplewizardstep' + (x - 1)).attr("class", "step-pane");
                $('#simplewizardstep' + (x + 1)).attr("class", "step-pane");
                $('#simplewizardstep' + x).attr("class", "active");
            },
            //به دلیل عدم استفاده کد ها کامنت شدند #2
            //ConfigurationMap: function () {
            //    if (true) {

            //    }
            //    else {
            //        return false;
            //    }
            //},
            //ConfigurationMap2: function () {
            //    if (true) {


            //    }
            //    else {
            //        return false;
            //    }
            //},
            //ConfigurationMap3: function () {
            //    if (true) {

            //        var crosshairIcon2 = {
            //            iconUrl: '/assets/vendor/libs/leaflet/images/marker-icon.png',
            //            iconSize: [37, 37], // size of the icon
            //            iconAnchor: [37, 37], // point of the icon which will correspond to marker's location
            //        };
            //        appMap3.addMarker({
            //            name: 'advanced-marker1',
            //            latlng: {
            //                lat: LatSource,
            //                lng: LngSource
            //            },
            //            icon: crosshairIcon2,
            //            popup: false
            //        });

            //        var crosshairIcon = {
            //            iconUrl: '~/assets/vendor/libs/leaflet/images/marker-icon.png',
            //            iconSize: [37, 37], // size of the icon
            //            iconAnchor: [37, 37], // point of the icon which will correspond to marker's location
            //        };
            //        appMap3.addMarker({
            //            name: 'advanced-marker2',
            //            latlng: {
            //                lat: LatDestination,
            //                lng: LngDestination
            //            },
            //            icon: crosshairIcon,
            //            popup: false
            //        });
            //        appMap3.map.fitBounds([[LatSource, LngSource], [LatDestination, LngDestination]]);
            //        //  appMap3.map.setView([LatDestination, LngDestination], 5);

            //    }
            //    else {
            //        return false;
            //    }
            //},
            fillgreadSelectedSenderfavorite: function () {
                if (true) {
                    var table1 = $("#gridfullsender");
                    myDataTable = table1.DataTable({
                        "lengthMenu": [[10, 25, 50, 100], [10, 25, 50, 100]],
                        "pageLength": 10,
                        "fixedHeader": true,
                        "processing": true,

                        "serverSide": true,
                        "searching": false,
                        "paging": true,
                        "ordering": false,
                        "scrollX": true,

                        "columns": [
                            { "data": "RowID", className: "RowID text-center", 'defaultContent': "" },
                            { "data": "isCompany", className: "isCompany text-center", 'defaultContent': "" },
                            { "data": "senderFirstName", className: "senderFirstName text-center", 'defaultContent': "" },
                            { "data": "senderLastName", className: "senderLastName text-center", 'defaultContent': "" },
                            //{ "data": "senderOfficeName", className: "senderOfficeName text-center", 'defaultContent': "" },
                            { "data": null, className: "selectSender text-center" },
                            { "data": null, className: "deleteSender text-center" },
                        ],
                        "columnDefs": [
                            {
                                "targets": [1],
                                "searchable": false,
                                "orderable": false,
                                "render": function (obj) {
                                    if (obj == true) {
                                        return "حقوقی";
                                    } else if (obj == false) {
                                        return "حقیقی";
                                    }
                                }
                            },
                            {
                                "targets": [4],
                                "searchable": false,
                                "orderable": false,
                                "render": function () {
                                    return "<button type='button' id='selectSender' name='selectSender' class='btn btn-primary'>انتخاب</button>";
                                }
                            },

                            {
                                "targets": [5],
                                "searchable": false,
                                "orderable": false,
                                "render": function () {

                                    return "<button type='button' id='deleteSender' name='deleteSender' class='btn btn-md  btn-outline-danger '><i  class='feather icon-trash-2'></i></button> ";
                                }
                            }],
                        "language": {
                            "url": "/assets/dist/Persian.json"
                        },
                        "ajax": {
                            "url": "/Barname/Document/fillgridesender",
                            "type": "POST",
                            "data": function (d) {
                                d.function = "fillgridesender",

                                    d.Sendersearch = $("#Sendersearchtext").val()

                            },
                            "error": function (error) {
                                $(table1).find("tbody tr").remove();

                                let obj = {};
                                try { obj = JSON.parse(error.responseText); } catch { }

                                let msg = obj.resultMessage || obj.ResultMessage || "خطا در پردازش درخواست";

                                $("#table1").append(
                                    `<tr><td colspan='100' style='text-align:center;'>${msg}</td></tr>`
                                );

                                $("#table1").parents("div.dataTables_wrapper").find("div.dataTables_processing").hide();

                                if (error.status == 401) {
                                    $("#loading").show()
                                    window.location = "/Barname/Account/Logout";
                                }
                            }
                        },
                        "initComplete": function (setting, json) {
                            //json.recordsTotal
                            myDataTable.ajax.reload();
                        }
                    });
                }
                else {
                    return false;
                }
            },
            fillgreadSelectedReciverfavorite: function () {
                if (true) {
                    var table1 = $("#gridfullreceiver");
                    myDataTableReceiver = table1.DataTable({
                        "lengthMenu": [[10, 25, 50, 100], [10, 25, 50, 100]],
                        "paging": true,
                        "fixedHeader": true,
                        "processing": true,
                        "serverSide": true,
                        "searching": false,
                        "ordering": false,
                        "bLengthChange": true,
                        "scrollX": true,
                        "dom": '<"top"i>rt<"bottom"flp><"clear">',
                        "info": false,
                        "columns": [
                            { "data": "RowID", className: "RowID text-center", "defaultContent": "" },
                            { "data": "isCompany", className: "isCompany text-center", "defaultContent": "" },
                            { "data": "receiverFirstName", className: "receiverFirstName text-center", "defaultContent": "" },
                            { "data": "receiverLastName", className: "receiverLastName text-center", "defaultContent": "" },
                            { "data": null, className: "selectReceiver text-center" },
                            { "data": null, className: "deleteReciver text-center" },
                        ],

                        "columnDefs": [
                            {
                                "targets": [1],
                                "searchable": false,
                                "orderable": false,
                                "render": function (obj) {
                                    if (obj == true) {
                                        return "حقوقی";
                                    } else if (obj == false) {
                                        return "حقیقی";
                                    }
                                }
                            },
                            {
                                "targets": [4],
                                "searchable": false,
                                "orderable": false,
                                "render": function () {
                                    return "<button type='button' id='selectReceiver' name='selectReceiver' class='btn  btn-primary'>انتخاب</button>";
                                }
                            },

                            {
                                "targets": [5],
                                "searchable": false,
                                "orderable": false,
                                "render": function () {
                                    return "<button type='button' id='deleteReciver' name='deleteReciver' class='btn btn-md  btn-outline-danger '><i  class='feather icon-trash-2'></i></button> ";
                                }
                            }],
                        "language": {
                            "url": "/assets/dist/Persian.json"
                        },
                        "ajax": {
                            "url": "/Barname/Document/fillgrideReceiver",
                            "type": "POST",
                            "data": function (d) {
                                d.function = "fillgrideReceiver",
                                    d.ReceiverSearch = $("#receiversearchtext").val()
                            },
                            "error": function (error) {
                                $(table1).find("tbody tr").remove();

                                let obj = {};
                                try { obj = JSON.parse(error.responseText); } catch { }

                                let msg = obj.resultMessage || obj.ResultMessage || "خطا در پردازش درخواست";

                                $("#table1").append(
                                    `<tr><td colspan='100' style='text-align:center;'>${msg}</td></tr>`
                                );

                                $("#table1").parents("div.dataTables_wrapper").find("div.dataTables_processing").hide();

                                if (error.status == 401) {
                                    $("#loading").show()
                                    window.location = "/Barname/Account/Logout";
                                }
                            }
                        },
                        "initComplete": function (setting, json) {
                            //json.recordsTotal
                            myDataTableReceiver.ajax.reload();
                        }
                    });
                }
                else {
                    return false;
                }
            },
            fillgreadSelectedDriverfavorite: function () {
                if (true) {
                    var table1 = $("#gridfulldriver");
                    myDataTableDriver = table1.DataTable({
                        "lengthMenu": [[10, 25, 50, 100], [10, 25, 50, 100]],
                        "pageLength": 10,
                        "fixedHeader": true,
                        "processing": true,
                        "serverSide": true,
                        "searching": false,
                        "paging": true,
                        "scrollX": true,
                        "ordering": false,
                        "columns": [
                            { "data": "RowID", className: "RowID text-center", 'defaultContent': "" },
                            { "data": "fullName", className: "fullName text-center", 'defaultContent': "" },
                            { "data": null, className: "selectDriver text-center" },
                            { "data": null, className: "deleteDriver text-center" },
                        ],
                        "columnDefs": [
                            {
                                "targets": [2],
                                "searchable": false,
                                "orderable": false,
                                "render": function () {
                                    return "<button type='button' id='selectDriver' name='selectDriver' class='btn  btn-primary'>انتخاب</button>";
                                }
                            },
                            {
                                "targets": [3],
                                "searchable": false,
                                "orderable": false,
                                "render": function () {
                                    return "<button id='deleteDriver' name='deleteDriver' type='button' class='btn btn-md  btn-outline-danger '><i  class='feather icon-trash-2'></i></button> ";
                                }
                            }],
                        "language": {
                            "url": "/assets/dist/Persian.json"
                        },
                        "ajax": {
                            "url": "/Barname/Document/fillgridDriver",
                            "type": "POST",
                            "data": function (d) {
                                d.function = "fillgridDriver",

                                    d.data = $("#driversearchtext").val()

                            },
                            "error": function (error) {
                                $(table1).find("tbody tr").remove();

                                let obj = {};
                                try { obj = JSON.parse(error.responseText); } catch { }

                                let msg = obj.resultMessage || obj.ResultMessage || "خطا در پردازش درخواست";

                                $("#table1").append(
                                    `<tr><td colspan='100' style='text-align:center;'>${msg}</td></tr>`
                                );

                                $("#table1").parents("div.dataTables_wrapper").find("div.dataTables_processing").hide();

                                if (error.status == 401) {
                                    $("#loading").show()
                                    window.location = "/Barname/Account/Logout";
                                }
                            }
                        },
                        "initComplete": function (setting, json) {
                            myDataTableDriver.ajax.reload();
                        }
                    });
                }
                else {
                    return false;
                }
            },
            fillgreadSelectedKalafavorite: function () {
                if (true) {
                    var table1 = $("#gridfullKala");
                    myDataTableKala = table1.DataTable({
                        "lengthMenu": [[10, 25, 50, 100], [10, 25, 50, 100]],
                        "pageLength": 10,
                        "fixedHeader": true,
                        "processing": true,

                        "serverSide": true,
                        "searching": false,
                        "paging": true,
                        "ordering": false,
                        "scrollX": true,

                        "columns": [
                            { "data": "RowID", className: "RowID text-center", 'defaultContent': "" },  //ردیف
                            { "data": "name", className: "name text-center", 'defaultContent': "" },  //نام کالا
                            { "data": "packTypeId", className: "packTypeId text-center", 'defaultContent': "" },  //نوع بسته بندی
                            { "data": "weight", className: "weight text-center", 'defaultContent': "" },  //وزن
                            { "data": "boxNum", className: "boxNum text-center", 'defaultContent': "" },  //تعداد بسته
                            { "data": null, className: "selectKala text-center" },  //انتخاب
                            { "data": null, className: "deleteKala text-center" },   //حذف
                        ],
                        "columnDefs": [
                            {
                                "targets": [2],
                                "searchable": false,
                                "orderable": false,
                                "render": function (data, type, row) {

                                    const typeItem = boxTypeList.find(t => t.id === data);
                                    return typeItem ? typeItem.name : '-'
                                }
                            },

                            {
                                "targets": [5],
                                "searchable": false,
                                "orderable": false,
                                "render": function () {
                                    return "<button type='button' id='selectKala' name='selectKala' class='btn btn-primary'>انتخاب</button>";
                                }
                            },

                            {
                                "targets": [6],
                                "searchable": false,
                                "orderable": false,
                                "render": function () {

                                    return "<button type='button' id='deleteKala' name='deleteKala' class='btn btn-md  btn-outline-danger '><i  class='feather icon-trash-2'></i></button> ";
                                }
                            }],
                        "language": {
                            "url": "/assets/dist/Persian.json"
                        },
                        "ajax": {
                            "url": "/Barname/Document/fillgrideKala",
                            "type": "POST",
                            "data": function (d) {
                                d.function = "fillgrideKala",

                                    d.Kalarsearch = $("#Kalasearchtext").val()

                            },
                            "error": function (error) {
                                $(table1).find("tbody tr").remove();

                                let obj = {};
                                try { obj = JSON.parse(error.responseText); } catch { }

                                let msg = obj.resultMessage || obj.ResultMessage || "خطا در پردازش درخواست";

                                $("#table1").append(
                                    `<tr><td colspan='100' style='text-align:center;'>${msg}</td></tr>`
                                );

                                $("#table1").parents("div.dataTables_wrapper").find("div.dataTables_processing").hide();

                                if (error.status == 401) {
                                    $("#loading").show()
                                    window.location = "/Barname/Account/Logout";
                                }
                            }
                           
                        },
                        "initComplete": function (setting, json) {
                            //json.recordsTotal
                            myDataTableKala.ajax.reload();
                        }
                    });
                }
                else {
                    return false;
                }
            },
            //---جدول علاقه مندی مبدا/مقصد
            fillgreadSelectedSenderAddressfavorite: function () {
                if (true) {
                    let table1 = $("#gridfulSenderAddress");
                    myDataTableSenderAddress = table1.DataTable({
                        "lengthMenu": [[10, 25, 50, 100], [10, 25, 50, 100]],
                        "pageLength": 10,
                        "fixedHeader": true,
                        "processing": true,
                        "serverSide": true,
                        "searching": false,
                        "paging": true,
                        "scrollX": true,
                        "ordering": false,
                        "defaultContent": "",
                        "columns": [
                            { "data": "RowID", className: "RowID text-center", defaultContent: "" },
                            { "data": "stateName", className: "receiverFullName text-center", defaultContent: "" },
                            { "data": "cityName", className: "receiverFullName text-center", defaultContent: "" },
                            { "data": "postalCode", className: "receiverFullName text-center", "defaultContent": "", },
                            { "data": null, className: "selectReceiver text-center" },
                            { "data": null, className: "deleteReciver text-center" },
                            { "data": null, className: "deleteReciver text-center" },
                        ],
                        "columnDefs": [
                            {
                                "targets": [4],
                                "searchable": false,
                                "orderable": false,
                                "data": null,
                                "render": function (data, type, full, meta) {

                                    let addressTitle = "";
                                    if (full.fullAddress != "") {
                                        addressTitle = `${full.fullAddress.substring(0, 15)}...`
                                    } else {
                                        addressTitle = "";
                                    }
                                    return `<lable class="text-left" data-toggle="tooltip" data-placement="right" title="${full?.fullAddress}" >
                                 ${full?.address}
                                   </lable>`;

                                },
                                "defaultContent": ""
                            },
                            {
                                "targets": [5],
                                "searchable": false,
                                "orderable": false,
                                "render": function () {
                                    return "<button type='button' id='selectSenderAddress' name='selectSenderAddress' class='btn  btn-primary'>انتخاب</button>";
                                }
                            },
                            {
                                "targets": [6],
                                "searchable": false,
                                "orderable": false,
                                "render": function () {
                                    return "<button id='deleteSenderAddress' name='deleteSenderAddress' type='button' class='btn btn-md  btn-outline-danger '><i  class='feather icon-trash-2'></i></button> ";
                                }
                            }],
                        "language": {
                            "url": "/assets/dist/Persian.json"
                        },
                        "ajax": {
                            "url": "/Barname/Document/fillGetPreAddress",
                            "type": "POST",
                            "data": function (d) {
                                d.function = "fillGetPreAddress",

                                    d.Source = true

                            },
                            "error": function (error) {
                                $(table1).find("tbody tr").remove();

                                let obj = {};
                                try { obj = JSON.parse(error.responseText); } catch { }

                                let msg = obj.resultMessage || obj.ResultMessage || "خطا در پردازش درخواست";

                                $("#table1").append(
                                    `<tr><td colspan='100' style='text-align:center;'>${msg}</td></tr>`
                                );

                                $("#table1").parents("div.dataTables_wrapper").find("div.dataTables_processing").hide();

                                if (error.status == 401) {
                                    $("#loading").show()
                                    window.location = "/Barname/Account/Logout";
                                }
                            }
                            
                        },
                        "initComplete": function (setting, json) {
                            /* myDataTableSenderAddress.ajax.reload();*/
                        }
                    });
                }
                else {
                    return false;
                }
            },
            fillgreadSelectedReciverAddressfavorite: function () {
                if (true) {
                    let table1 = $("#gridfulReciverAddress");
                    myDataTableReciverAddress = table1.DataTable({
                        "lengthMenu": [[10, 25, 50, 100], [10, 25, 50, 100]],
                        "pageLength": 10,
                        "fixedHeader": true,
                        "processing": true,
                        "serverSide": true,
                        "searching": false,
                        "paging": true,
                        "scrollX": true,
                        "ordering": false,
                        "defaultContent": "",
                        "columns": [
                            { "data": "RowID", className: "RowID text-center", 'defaultContent': "" },
                            { "data": "stateName", className: "receiverFullName text-center", 'defaultContent': "" },
                            { "data": "cityName", className: "receiverFullName text-center", 'defaultContent': "" },
                            { "data": "postalCode", className: "receiverFullName text-center", "defaultContent": "", },
                            { "data": null, className: "receiverFullName text-center" },
                            { "data": null, className: "selectReceiver text-center" },
                            { "data": null, className: "deleteReciver text-center" },
                        ],
                        "columnDefs": [
                            {
                                "targets": [4],
                                "searchable": false,
                                "orderable": false,
                                "data": null,
                                "render": function (data, type, full, meta) {

                                    let addressTitle = "";
                                    if (full.fullAddress != "") {
                                        addressTitle = `${full.fullAddress.substring(0, 15)}...`
                                    } else {
                                        addressTitle = "";
                                    }
                                    return `<lable class="text-left" data-toggle="tooltip" data-placement="right" title="${full?.fullAddress}" >
                                 ${full?.address}
                                   </lable>`;

                                },
                                "defaultContent": ""
                            },
                            {
                                "targets": [5],
                                "searchable": false,
                                "orderable": false,
                                "render": function () {
                                    return "<button type='button' id='selectReciverAddress' name='selectReciverAddress' class='btn  btn-primary'>انتخاب</button>";
                                }
                            },
                            {
                                "targets": [6],
                                "searchable": false,
                                "orderable": false,
                                "render": function () {
                                    return "<button id='deleteReciverAddress' name='deleteReciverAddress' type='button' class='btn btn-md  btn-outline-danger '><i  class='feather icon-trash-2'></i></button> ";
                                }
                            }],
                        "language": {
                            "url": "/assets/dist/Persian.json"
                        },
                        "ajax": {
                            "url": "/Barname/Document/fillGetPreAddress",
                            "type": "POST",
                            "data": function (d) {
                                d.function = "fillGetPreAddress",

                                    d.Source = false

                            },
                            "error": function (error) {
                                $(table1).find("tbody tr").remove();

                                let obj = {};
                                try { obj = JSON.parse(error.responseText); } catch { }

                                let msg = obj.resultMessage || obj.ResultMessage || "خطا در پردازش درخواست";

                                $("#table1").append(
                                    `<tr><td colspan='100' style='text-align:center;'>${msg}</td></tr>`
                                );

                                $("#table1")
                                    .parents("div.dataTables_wrapper")
                                    .find("div.dataTables_processing")
                                    .hide();

                                if (error.status == 401) {
                                    $("#loading").show()
                                    window.location = "/Barname/Account/Logout";
                                }
                            }
                            
                        },
                        "initComplete": function (setting, json) {

                        }
                    });
                }
                else {
                    return false;
                }
            },
            //----------------------------
            fillgreadSelectedLoadfavorite: function () {
                if (true) {
                    $("#loading").show();
                    var html = ``;
                    $("#gridfullLoaddata").empty();

                    for (var i = 0; i < loadList.length; i++) {
                        var Item = loadList[i];
                        if (Item.Wheight)
                            // totalWeight += parseFloat(Item.Wheight);

                            totalWeight = loadList.reduce((sum, x) => sum + (parseFloat(x.Wheight) || 0), 0);
                        /*<td class=' editLoad text-center' ><button type='button' name='editLoadBtn' ID='${Item.ID}' ><i ' class='fa fa-edit' style='font-size:24px'></i></button></td>*/
                        //<td class=' selectLoad text-center' ><button type='button' ID='${Item.ID}' name='selectLoad' class='btn  btn-primary'>انتخاب</button></td>
                        html = html + `
                                    <tr>
                                       <th scope="row" class=' selectLoad text-center' >${i + 1}</th>
                                       <td class=' selectLoad text-center'>${Item.Name}</td>
                                       
                                       
                                       <td class=' deleteLoad text-center' > <button type='button' class='btn  btn-outline-danger ' name='deleteLoad'  ID='${Item.ID}' > حذف</button></td>
                                   </tr>
                         `;
                    }

                    $("#gridfullLoaddata").append(html);

                    $("#totalWeight").text(totalWeight);  //مجموع وزن کالاها

                    binding.bindEditBtns();
                    binding.bindSelectedBtns();
                    binding.binddeleteLoadBtns();
                    $("#loading").hide();

                }
                else {
                    return false;
                }
            },
            fillgreadSelectedPelakfavorite: function () {

                if (true) {
                    var table1 = $("#gridfullPelak");
                    myDataTablePelak = table1.DataTable({
                        "lengthMenu": [[10, 25, 50, 100], [10, 25, 50, 100]],
                        "pageLength": 10,
                        "fixedHeader": true,
                        "processing": true,
                        "serverSide": true,
                        "searching": false,
                        "paging": true,
                        "scrollX": true,
                        "ordering": false,
                        "columns": [
                            { "data": "RowID", className: "RowIDLoad text-center", 'defaultContent': "" },
                            { "data": null, className: "productName text-center" },
                            { "data": null, className: "selectPelak text-center" },
                            { "data": null, className: "deletePelak text-center" },
                        ],
                        "columnDefs": [
                            {
                                "targets": [1],
                                "searchable": false,
                                "orderable": false,
                                "render": function (obj) {

                                    if (obj.freeZoneNo == null) {


                                        var resultCombo = generalJS.GetPelakChar(obj.t3);
                                        var result = obj.t1 + "|" + obj.t4 + " " + resultCombo + " " + obj.t2;

                                    }
                                    else {
                                        $("#pelakTypeCombo").val(obj.freeZoneCode);
                                        var comboAzad = $("#pelakTypeCombo option:selected").text();
                                        if (obj.t3 == null) {
                                            obj.t3 = "";
                                            var result = comboAzad + "|" + obj.freeZoneNo;
                                        }
                                        else {
                                            var result = comboAzad + "|" + obj.freeZoneNo + " -" + obj.t3;
                                        }


                                    }
                                    return result;
                                },
                                "defaultContent": ""
                            },
                            {
                                "targets": [2],
                                "searchable": false,
                                "orderable": false,
                                "render": function () {
                                    return "<button type='button' id='selectPelak' name='selectPelak' class='btn  btn-primary'>انتخاب</button>";
                                }
                            },
                            {
                                "targets": [3],
                                "searchable": false,
                                "orderable": false,
                                "render": function () {
                                    return "<button type='button' id='deletePelak' name='deletePelak' class='btn btn-md  btn-outline-danger '><i  class='feather icon-trash-2'></i></button> ";
                                }
                            }],
                        "language": {
                            "url": "/assets/dist/Persian.json"
                        },
                        "ajax": {
                            "url": "/Barname/Document/fillgridPelak",
                            "type": "POST",
                            "data": function (d) {
                                d.function = "fillgridPelak",
                                    d.data = id
                            },
                            "error": function (error) {
                                $(table1).find("tbody tr").remove();

                                let obj = {};
                                try { obj = JSON.parse(error.responseText); } catch { }

                                let msg = obj.resultMessage || obj.ResultMessage || "خطا در پردازش درخواست";

                                $("#table1").append(
                                    `<tr><td colspan='100' style='text-align:center;'>${msg}</td></tr>`
                                );

                                $("#table1").parents("div.dataTables_wrapper").find("div.dataTables_processing").hide();
                            }
                        },
                        "initComplete": function (setting, json) {
                            myDataTablePelak.ajax.reload();
                        }
                    });
                }
                else {
                    return false;
                }
            },
            fillPreSender: function () {
                if (true) {
                    if ($("#ddSender option:selected").val() == "") {
                        $("#loading").show();
                        $.ajax({
                            url: "/Account/FormDocumentDetailsRegister.aspx",
                            function: "fillPreSender",
                            data: {/* selectvalue: selectedValue */ },
                            success: function (Doc) {
                                $("#loading").hide();
                                $("#ddSender option").not('option[value=""]').remove();
                                var ddSender = $("#ddSender");
                                $.each(Doc, function () {
                                    ddSender.append("<option value=" + this.id + ">" + this.senderFullName + "</option>");
                                });
                            },
                            error: function (error) {
                                $("#loading").hide();
                                toaster.toast("error", "خطا", error.statusText)
                            }
                        });

                    }
                }
                else {
                    return false;
                }
            },
            fillPreReceiver: function () {
                if (true) {
                    if ($("#ddReceiver option:selected").val() == "") {
                        $("#loading").show();
                        $.ajax({
                            url: "/Account/FormDocumentDetailsRegister.aspx",
                            function: "fillPreReceiver",
                            data: {/* selectvalue: selectedValue */ },
                            success: function (Doc) {
                                $("#loading").hide();
                                $("#ddReceiver option").not('option[value=""]').remove();
                                var ddReceiver = $("#ddReceiver");
                                $.each(Doc, function () {
                                    ddReceiver.append("<option value=" + this.id + ">" + this.receiverFullName + "</option>");
                                });
                            },
                            error: function (error) {
                                $("#loading").hide();
                                toaster.toast("error", "خطا", error.statusText)
                            }
                        });
                    }
                }
                else {
                    return false;
                }
            },
            fillBoxType: function () {
                if (true) {
                    $("#loading").show();
                    $.ajax({
                        url: "/Barname/Document/fillBoxType",
                        data: { /*txtkala: selectedValue */ },
                        success: function (res) {
                            res = JSON.parse(res)
                            let Doc = res.obj
                            boxTypeList = Doc;

                            $("#loading").hide();
                            $("select[name='ddBoxType']").empty();
                            var ddBoxType = $("select[name='ddBoxType']");
                            ddBoxType.append("<option value=''>انتخاب کنید</option>");
                            $.each(Doc, function () {

                                ddBoxType.append("<option value=" + this.id + ">" + this.name + "</option>");

                            });
                            $("select[name='ddBoxTypeModal']").empty();
                            var ddBoxTypeModal = $("select[name='ddBoxTypeModal']");
                            ddBoxTypeModal.append("<option value=''>انتخاب کنید</option>");
                            $.each(Doc, function () {

                                ddBoxTypeModal.append("<option value=" + this.id + ">" + this.name + "</option>");

                            });

                        },
                        error: function (error) {
                            $("#loading").hide();
                            toaster.toast("error", "خطا", error.statusText)
                        }
                    });
                    //}
                }
                else {
                    return false;
                }
            },

            fillStates: function () {
                if (true) {
                    $("#loading").show();
                    $.ajax({
                        url: "/Barname/Document/fillStates",
                        data: {/* selectvalue: selectedValue */ },
                        success: function (Doc) {
                            debugger
                            //Doc = JSON.parse(Doc).obj
                       
                            $("#loading").hide();
                            $("#ddStateSource option").not('option[value=""]').remove();
                            var ddStateSource = $("#ddStateSource");
                            $.each(Doc, function () {
                                ddStateSource.append("<option value=" + this.id + ">" + this.name + "</option>");
                            });
                            $("#ddStateDest option").not('option[value=""]').remove();
                            var ddStateDest = $("#ddStateDest");
                            $.each(Doc, function () {
                                ddStateDest.append("<option value=" + this.id + ">" + this.name + "</option>");
                            });
                            $("#ddState option").not('option[value=""]').remove();
                            var ddState = $("#ddState");
                            $.each(Doc, function () {
                                ddState.append("<option value=" + this.id + ">" + this.name + "</option>");
                            });

                        },
                        error: function (error) {

                            $("#loading").hide();
                            let raw = error.responseText || "";
                            let jsonPart = null;


                            let start = raw.indexOf("{");
                            let end = raw.lastIndexOf("}");

                            if (start !== -1 && end !== -1 && end > start) {
                                let possibleJson = raw.substring(start, end + 1);

                                try {
                                    jsonPart = JSON.parse(possibleJson);
                                } catch (e) {
                                    console.log("JSON parse failed:", e);
                                }
                            }


                            let msg = jsonPart?.resultMessage || jsonPart?.ResultMessage || "خطا در پردازش درخواست";


                            toaster.toast("error", "خطا", msg);

                            if (error.status == 401) {
                                $("#loading").show()
                                window.location = "/Barname/Account/Logout";
                            }

                        }
                    });
                }
                else {
                    return false;
                }
            },
            fillStatesList: function () {

                if (true) {
                    $("#loading").show();
                    $.ajax({
                        url: "/Barname/Document/fillStates",
                        data: {/* selectvalue: selectedValue */ },
                        success: function (result) {
                            $("#loading").hide();
                            $("#OrginState").empty();
                            $("#OrginState").append("<option value='' > انتخاب کنید </option>");
                            $("#DestinationState").empty();
                            $("#DestinationState").append("<option value='' > انتخاب کنید </option>");

                            if (result.resultCode == 0) {

                                result.obj.map(x => {

                                    $("#OrginState").append(`<option value='${x.id}' >  ${x.name} </option>`);
                                    $("#DestinationState").append(`<option value='${x.id}' >  ${x.name} </option>`);

                                });
                            }



                        },
                        error: function (error) {
                            $("#loading").hide();
                            toaster.toast("error", "خطا", error.statusText)
                        }
                    });
                }
                else {
                    return false;
                }
            },

            GetDocumentById: function () {
                if (true) {
                    $("#loading").show();
                    $.ajax({
                        url: "/Barname/Document/GetDocumentById",
                        data: { id: id },
                        success: function (result) {
                            debugger
                            $("#loading").hide();
                            IT_cost = result.IT_cost;
                            RowID = result.RowID;
                            avarez = result.avarez;
                            bearingCost = result.bearingCost;
                            canIssue = result.canIssue;
                            date = result.date;
                            dateFarsi = result.dateFarsi;
                            destAddress = result.destAddress;
                            destCityId = result.destCityId;
                            destCityName = result.destCityName;
                            destPostalCode = result.destPostalCode;
                            destStateId = result.destStateId;
                            destStateName = result.destStateName;
                            docNo = result.docNo;
                            driverCertificateNumber = result.driverCertificateNumber;
                            driverFirstName = result.driverFirstName;
                            driverFullName = result.driverFullName;
                            driverHaveCertificate = result.driverHaveCertificate;
                            driverImage = result.driverImage;
                            driverLastName = result.driverLastName;
                            driverMobile = result.driverMobile;
                            driverNationalCode = result.driverNationalCode;
                            driverRank = result.driverRank;
                            id = result.id;
                            insurance = result.insurance;
                            loadDescription = result.loadDescription;
                            loadId = result.loadId;
                            loadName = result.loadName;
                            loadTypeName = result.loadTypeName;
                            loadWeight = result.loadWeight;
                            notifyCost = result.notifyCost;
                            packTypeId = result.packTypeId;
                            packTypeName = result.packTypeName;
                            postRent = result.postRent;
                            preRent = result.preRent;
                            receiverFirstName = result.receiverFirstName;
                            receiverLastName = result.receiverLastName;
                            ReceiverOfficeName = result.ReceiverOfficeName;
                            receiverMobile = result.receiverMobile;
                            receiverNationalCode = result.receiverNationalCode;
                            receiverPostalCode = result.receiverPostalCode;
                            receiverTelNumber = result.receiverTelNumber;
                            rent = result.rent;
                            rowData = result.rowData;
                            senderFirstName = result.senderFirstName;
                            senderLastName = result.senderLastName;
                            SenderOfficeName = result.SenderOfficeName;
                            senderMobile = result.senderMobile;
                            senderNationalCode = result.senderNationalCode;
                            senderPostalCode = result.senderPostalCode;
                            senderTelNumber = result.senderTelNumber;
                            sourceAddress = result.sourceAddress;
                            sourceCityId = result.sourceCityId;
                            sourceCityName = result.sourceCityName;
                            sourcePostalCode = result.sourcePostalCode;
                            sourceStateId = result.sourceStateId;
                            sourceStateName = result.sourceStateName;
                            status = result.status;
                            statusName = result.statusName;
                            submitterId = result.submitterId;
                            t1 = result.t1;
                            t2 = result.t2;
                            t3 = result.t3;
                            t4 = result.t4;
                            tag = result.tag;
                            time = result.time;
                            toPay = result.toPay;
                            truckCapacity = result.truckCapacity;
                            truckCapacityTo = result.truckCapacityTo;
                            truckHave3rdInsurance = result.truckHave3rdInsurance;
                            truckHaveCertificate = result.truckHaveCertificate;
                            truckId = result.truckId;
                            truckTagType = result.truckTagType;
                            truckType = result.truckType;
                            type = result.type;
                            userIdDriver = result.userIdDriver;
                            value = result.value;
                            zoneCityIds = result.zoneCityIds;
                            zoneStateIds = result.zoneStateIds;
                            havecertificateinload = driverHaveCertificate;
                            shippingStartDate = result.shippingStartDate
                        },
                        error: function (error) {
                            $("#loading").hide();
                            toaster.toast("error", "خطا", error.statusText)
                        }
                    });
                }
                else {
                    return false;
                }
            },
            showDetailsGetDocumentById: function () {
                if (true) {

                    IT_cost; IT_cost;
                    RowID = RowID;
                    avarez = avarez;
                    bearingCost = bearingCost;
                    canIssue = "true";
                    date = date;
                    dateFarsi = dateFarsi;
                    destAddress = $("#txtAddressDest").val();
                    //destCityId= $("#ddCityDest").val();
                    destCityName = $("#ddCityDest").val();
                    destPostalCode = $("#destPostalCode").val();
                    destStateId = $("#ddStateDest").val();
                    destStateName = $("#ddStateDest").val();
                    docNo = docNo;
                    driverCertificateNumber = $("#DriverNumberDriverLicense").val();
                    driverFirstName = firstName;
                    driverFullName = $("#DriverFullName").val();
                    driverHaveCertificate = driverHaveCertificate;
                    driverImage = driverImage;
                    driverLastName = lastName;
                    driverMobile = driverMobile;
                    driverNationalCode = $("#txtDriverSearch").val();
                    driverRank = $("#DriverRating").val();
                    id = id;
                    insurance = $("#chkInsurance").val();
                    loadDescription = loadDescription;

                    loadWeight = loadWeight;
                    notifyCost = $("#txtnotifyCost").val();
                    packTypeId = packTypeId;
                    packTypeName = packTypeName;
                    postRent = $("#txtPasKeraye").val();
                    preRent = $("#txtPishKeraye").val();
                    receiverFirstName = $("#txtReceiverFirstName").val();
                    receiverLastName = $("#txtReceiverLastName").val();
                    receiverOfficeName = $("#txtReceiverOfficeName").val() ? $("#txtReceiverOfficeName").val() : "";
                    receiverMobile = $("#txtReceiverMobile").val();
                    receiverNationalCode = $("#txtReceiverNationalCode").val();
                    receiverPostalCode = $("#txtReceiverPostalCode").val();
                    receiverTelNumber = $("#txtReceiverTell").val();
                    rent = $("#txtkeraye").val();
                    rowData = rowData;
                    senderFirstName = $("#txtSenderFirstName").val();
                    senderLastName = $("#txtSenderLastName").val();
                    SenderOfficeName = $("#txtSenderOfficeName").val() ? $("#txtSenderOfficeName").val() : "";
                    senderMobile = $("#txtSenderMobile").val();
                    senderNationalCode = $("#txtSenderNationalCode").val();
                    senderPostalCode = $("#txtSenderPostalCode").val();
                    senderTelNumber = $("#txtSenderTell").val();
                    sourceAddress = $("#txtAddressSource").val();
                    sourceCityId = $("#ddCitySource").val();
                    sourceCityName = $("#ddCitySource").val();
                    sourcePostalCode = $("#sourcePostalCode").val();
                    if ($("#sourcePostalCode").val() == null) {
                        sourcePostalCode = $("#SourcePostalCodeFromMap").val()
                    }
                    sourceStateId = $("#ddStateSource").val();
                    sourceStateName = $("#ddStateSource").val();
                    status = "0";
                    statusName = statusName;
                    submitterId = submitterId;

                    rest1 = t1 == null ? tajmiT1 : t1;
                    rest2 = t2 == null ? tajmiT2 : t2;

                    /*rest3 = $("select[id='pelakCombo'] option:selected").text();*/
                    if (t4 != "") {
                        rest3 = $("select[id='pelakCombo'] option:selected").val();
                    }
                    else {

                        rest3 = t3 == null ? tajmiT3 : t3;
                    }
                    rest4 = t4 == null ? tajmiT4 : t4;
                    tag = tag;
                    time = time;
                    toPay = toPay;
                    truckCapacity = $("#CapacityFrom").val();
                    truckCapacityTo = $("#CapacityTo").val();
                    truckHave3rdInsurance = have3rd;
                    truckHaveCertificate = havelicense;
                    truckId = truckId;
                    truckTagType = truckTagType;
                    truckType = $("#TypeofLoader").val();
                    type = "0";
                    userIdDriver = userIdDriver;
                    value = value1;
                    zoneCityIds = zoneCityIds;
                    zoneStateIds = zoneStateIds;
                    stepSource = "Source";
                    stepDest = "Dest";
                    fuelType = fuelType;
                    SendSMS = SendSMS;
                    loadList = loadList;
                    lngSource = LngSource;
                    latSource = LatSource;
                    LatDestination = LatDestination;
                    LngDestination = LngDestination;
                    FormShippingDocumentationSystemClick.showDetails();

                }
                else {
                    return false;
                }
            },
            Comma: function (Num) {

                Num += '';
                Num = Num.replace(',', '');
                Num = Num.replace(',', '');
                Num = Num.replace(',', '');
                Num = Num.replace(',', '');

                Num = Num.replace(',', '');
                Num = Num.replace(',', '');
                Num = Num.replace(',', '');
                Num = Num.replace(',', '');

                Num = Num.replace(',', '');
                Num = Num.replace(',', '');
                Num = Num.replace(',', '');
                Num = Num.replace(',', '');

                x = Num.split('.');
                x1 = x[0];
                x2 = x.length > 1 ? '.' + x[1] : '';
                var rgx = /(\d+)(\d{3})/;
                while (rgx.test(x1))
                    x1 = x1.replace(rgx, '$1' + ',' + '$2');
                return x1 + x2;
            },
        }
    }();
    var FormShippingDocumentationSystemClick = function () {
        return {
            //--------sender--------------------
            functionSender: function () {

                objformhelper.validate.init("frmSender")
                    .success(function () {

                        generalCls.SetWizard(2);
                    })
                    .error(function () {
                        return false;
                    });


            },
            SenderUpdateNext: function () {
                if (true) {
                    objformhelper.validate.init("frmSender")
                        .success(function () {

                            if (success.code == 1) {
                                //        generalCls.GetDocumentById();
                                generalCls.SetWizard(2);
                            }
                            else {
                                toaster.toast("error", "پیغام خطا", success.message)
                            }

                        })
                        .error(function () {
                            return false;
                        });
                }
                else {
                    return false;
                }
            },
            SenderReturn: function () {

                window.location = "Main.aspx";
            },

            showgrideSender: function () {
                $("#showgrideSender").val("");
                $("#frmSender").hide();
                $("#frmSenderFavorit").show();
                myDataTable.ajax.reload();
            },
            btnDeleteDetailsSender: function () {

                var row = $(this).parents('tr');
                /*   generalJS.setSession("keyDoc", myDataTable.row(row).data()['id']);*/
                idSender = myDataTable.row(row).data()['id'];

                if (true) {
                    FormShippingDocumentationSystemClick.deleteSender();

                }
                else {
                    return false;
                }
            },
            deleteSender: function () {

                if (true) {
                    $("#loading").show();
                    $.ajax({
                        url: "/Barname/Document/btnDeletePreSender",
                        data: {
                            idSender: idSender,
                        },
                        success: function (success) {
                           // success = JSON.parse(success)
                            $("#loading").hide();
                            if (success.resultCode == 200) {
                                toaster.toast("success", "پیغام سیستم", success.resultMessage);
                                myDataTable.ajax.reload();
                            }
                            else {
                                
                                toaster.toast("error", "خطا", success.resultMessage);
                            }
                        },
                        error: function (error) {
                            
                            $("#loading").hide();
                            let raw = error.responseText || "";
                            let jsonPart = null;


                            let start = raw.indexOf("{");
                            let end = raw.lastIndexOf("}");

                            if (start !== -1 && end !== -1 && end > start) {
                                let possibleJson = raw.substring(start, end + 1);

                                try {
                                    jsonPart = JSON.parse(possibleJson);
                                } catch (e) {
                                    console.log("JSON parse failed:", e);
                                }
                            }


                            let msg = jsonPart?.resultMessage || jsonPart?.ResultMessage || "خطا در پردازش درخواست";


                            toaster.toast("error", "خطا", msg);

                            if (error.status == 401) {
                                $("#loading").show()
                                window.location = "/Barname/Account/Logout";
                            }

                        }
                    });
                }
                else {
                    return false;
                }
            },
            GetCitiesSource: function () {
                let selectedValue = $("#OrginState").val();
                if (true) {
                    $("#loading").show();
                    $.ajax({
                        url: "/Barname/Document/GetCities",


                        data: { ddState: selectedValue },
                        success: function (result) {

                            $("#loading").hide();
                            $("#OrginCity").empty();
                            $("#OrginCity").append("<option value='' > انتخاب کنید </option>");

                            if (!!result) {

                                result.map(x => {

                                    $("#OrginCity").append(`<option value='${x.id}' >  ${x.name} </option>`);

                                });
                            }



                        },
                        error: function (error) {
                            $("#loading").hide();
                            toaster.toast("error", "خطا", error.statusText)
                        }
                    });
                }
                else {
                    return false;
                }
            },
            GetCitiesDestination: function () {
                let selectedValue = $("#DestinationState").val();
                if (true) {
                    $("#loading").show();
                    $.ajax({
                        url: "/Barname/Document/GetCities",
                        data: { ddState: selectedValue },
                        success: function (result) {

                            $("#loading").hide();
                            $("#DestinationCity").empty();
                            $("#DestinationCity").append("<option value='' > انتخاب کنید </option>");

                            if (!!result) {

                                result.map(x => {

                                    $("#DestinationCity").append(`<option value='${x.id}' >  ${x.name} </option>`);

                                });
                            }



                        },
                        error: function (error) {
                            $("#loading").hide();
                            toaster.toast("error", "خطا", error.statusText)
                        }
                    });
                }
                else {
                    return false;
                }
            },
            btneditDeatailSender: function () {
                var row = $(this).parents('tr');
                /*  generalJS.setSession("keyDoc", myDataTable.row(row).data()['id']);*/
                idSender = myDataTable.row(row).data()['id'];
                senderFirstName = myDataTable.row(row).data()['senderFirstName'];
                senderLastName = myDataTable.row(row).data()['senderLastName'];
                senderNationalCode = myDataTable.row(row).data()['senderNationalCode'];
                senderMobile = myDataTable.row(row).data()['senderMobile'];
                senderTelNumber = myDataTable.row(row).data()['senderTelNumber'];
                senderPostalCode = myDataTable.row(row).data()['senderPostalCode'];
                if (true) {
                    $("#txtSenderFirstNameModal").val("");
                    $("#txtSenderMobileModal").val("");
                    $("#txtSenderNationalCodeModal").val("");
                    $("#txtSenderTellModal").val("");
                    $("#txtPostalCodeModal").val("");
                    //---------------------------------------------
                    $("#txtSenderFirstNameModal").val(senderFirstName).trigger("change");
                    $("#txtSenderMobileModal").val(senderMobile).trigger("change");
                    $("#txtSenderNationalCodeModal").val(senderNationalCode).trigger("change");
                    $("#txtSenderTellModal").val(senderTelNumber).trigger("change");
                    $("#txtPostalCodeModal").val(senderPostalCode).trigger("change");

                    $("#modaleditsender").modal('show');

                }
                else {
                    return false;
                }
            },
            UpdateSender: function () {
                $("#loading").show();
                if (true) {
                    objformhelper.validate.init("frmmodalsender")
                        .success(function () {
                            $.ajax({
                                url: "/Account/FormDocumentDetailsRegister.aspx",
                                function: "btnUpdatePreSender",
                                data: {
                                    idSender: idSender,
                                    senderFullName: $("#txtSenderFullNameModal").val(),
                                    senderNationalCode: $("#txtSenderNationalCodeModal").val(),
                                    senderMobile: $("#txtSenderMobileModal").val(),
                                    senderTelNumber: $("#txtSenderTellModal").val(),
                                    senderPostalCode: $("#txtPostalCodeModal").val(),
                                },
                                success: function (success) {
                                    $("#loading").hide();
                                    if (success.resultCode == 200) {
                                        toaster.toast("success", "پیغام سیستم", success.resultMessage);
                                        myDataTable.ajax.reload();
                                        $('#modaleditsender').modal("hide");
                                    }
                                    else {

                                        toaster.toast("error", "خطا", success.resultMessage);
                                    }
                                },
                                error: function (error) {
                                    $("#loading").hide();
                                    toaster.toast("error", "خطا", error.statusText);

                                }
                            });
                        })
                        .error(function () {
                            return false;
                        });
                }
                else {
                    return false;
                }
            },
            selectSender: function () {
                if (true) {

                    $("#txtSenderFirstName").val("");
                    $("#txtSenderOfficeName").val("");
                    $("#loading").show();
                    var row = $(this).parents('tr');
                    var Datas = myDataTable.row(row).data();
                    var senderFirstName = Datas.senderFirstName;
                    var senderLastName = Datas.senderLastName;
                    var IsHoghughi = Datas.isCompany;
                    /*    generalJS.setSession("keyDoc", myDataTable.row(row).data()['id']);*/
                    idSender = myDataTable.row(row).data()['id'];

                    /* $("#txtSenderLastName").val(myDataTable.row(row).data()['senderLastName']).trigger("change");*/
                    $("#senderSelectType").val(myDataTable.row(row).data()['isCompany'] ? 2 : 1).trigger("change");  //نوع بارنامه
                    $("#txtSenderNationalCode").val(myDataTable.row(row).data()['senderNationalCode']).trigger("change");
                    $("#txtSenderMobile").val(myDataTable.row(row).data()['senderMobile']).trigger("change");
                    $("#txtSenderTell").val(myDataTable.row(row).data()['senderTelNumber']).trigger("change");
                    $("#txtSenderPostalCode").val(myDataTable.row(row).data()['senderPostalCode']).trigger("change");
                    if (myDataTable.row(row).data()['senderFirstName'] != null) {
                        $("#frmSender input[name='senderFirstName']").removeAttr("required");
                        $("#frmSender input[name='senderFirstName']").removeAttr("data-fv-notempty-message");
                        $("#frmSender  input[name='senderFirstName']").parents().parents().removeClass("has-success has-error");
                        //$("#frmSender").formValidation('removeField', $("#frmSender input[name='senderFullName']"));
                        $("#loading").hide();
                    }
                    else {
                        $("input[name='senderFirstName']").attr("required", "senderFirstName");
                        $("input[name='senderFirstName']").attr("data-fv-notempty-message", "وارد کردن مقدار اجباری است");
                        //$("#frmSender").formValidation('addField', $("#frmSender input[name='senderFullName']"));
                        //objformhelper.init("frmSender");
                    }

                    if (myDataTable.row(row).data()['senderLastName'] != null) {
                        $("#frmSender input[name='senderLastName']").removeAttr("required");
                        $("#frmSender input[name='senderLastName']").removeAttr("data-fv-notempty-message");
                        $("#frmSender  input[name='senderLastName']").parents().parents().removeClass("has-success has-error");
                        //$("#frmSender").formValidation('removeField', $("#frmSender input[name='senderFullName']"));
                        $("#loading").hide();
                    }
                    else {
                        $("input[name='senderLastName']").attr("required", "senderLastName");
                        $("input[name='senderLastName']").attr("data-fv-notempty-message", "وارد کردن مقدار اجباری است");
                        //$("#frmSender").formValidation('addField', $("#frmSender input[name='senderFullName']"));
                        //objformhelper.init("frmSender");
                    }
                    $("#loading").hide();
                    $("#frmSender").show();
                    $("#frmSenderFavorit").hide();

                    if (IsHoghughi == false) {

                        $("#txtSenderFirstName").val(senderFirstName).trigger("change");
                        $("#txtSenderLastName").val(senderLastName).trigger("change");
                    } else {
                        $("#txtSenderOfficeName").val(senderFirstName).trigger("change");

                    }
                }
                else {
                    return false;
                }
            },
            showuser: function () {
                if (true) {
                    $.ajax({
                        url: "/Account/FormGrid.aspx",
                        function: "ShowUserName",
                        data: {},
                        success: function (Doc) {
                            $("#username").text(result);
                        },
                        error: function (error) {

                            toaster.toast("error", "خطا", error.statusText);
                        }
                    });
                }
                else {
                    return false;
                }
            },

            btnRegPreSender: function () {

                if (true) {
                    if ($("#senderSelectType").val() == 1) {
                        var selectIsCompany = false;

                    } else {
                        var selectIsCompany = true;
                    }
                    objformhelper.validate.init("frmSender")
                        .success(function () {

                            if (true) {
                                $("#loading").show();
                                $.ajax({
                                    url: "/Barname/Document/btnRegPreSender",
                                    data: {
                                        txtSenderFirstName: $("#txtSenderFirstName").val() ? $("#txtSenderFirstName").val() : $("#txtSenderOfficeName").val(),
                                        txtSenderLastName: $("#txtSenderLastName").val(),
                                        //txtSenderOffice: $("#txtSenderFirstName").val(),
                                        txtSenderMobile: $("#txtSenderMobile").val(),
                                        txtSenderNationalCode: $("#txtSenderNationalCode").val(),
                                        txtSenderTell: $("#txtSenderTell").val(),
                                        txtSenderPostalCode: $("#txtSenderPostalCode").val(),
                                        IsCompany: selectIsCompany,
                                    },
                                    success: function (success) {
                                        $("#loading").hide();
                                       // success = JSON.parse(success)
                                        if (success.resultCode == 200) {
                                            toaster.toast("success", "پیغام سیستم", success.resultMessage)


                                        }
                                        else {

                                            toaster.toast("error", "خطا", success.resultMessage)
                                        }

                                    },
                                    error: function (error) {

                                        $("#loading").hide();
                                        let raw = error.responseText || "";
                                        let jsonPart = null;


                                        let start = raw.indexOf("{");
                                        let end = raw.lastIndexOf("}");

                                        if (start !== -1 && end !== -1 && end > start) {
                                            let possibleJson = raw.substring(start, end + 1);

                                            try {
                                                jsonPart = JSON.parse(possibleJson);
                                            } catch (e) {
                                                console.log("JSON parse failed:", e);
                                            }
                                        }


                                        let msg = jsonPart?.resultMessage || jsonPart?.ResultMessage || "خطا در پردازش درخواست";


                                        toaster.toast("error", "خطا", msg);

                                        if (error.status == 401) {
                                            $("#loading").show()
                                            window.location = "/Barname/Account/Logout";
                                        }

                                    }
                                });
                            }
                            else {
                                return false;
                            }
                        })
                        .error(function (e) {

                            return false;
                        });
                }
                else {
                    return false;
                }
            },
            SendergridReturn: function () {
                if (true) {
                    $("#loading").hide();
                    $("#frmSender").show();
                    $("#frmSenderFavorit").hide();
                }
                else {
                    return false;
                }

            },
            SendBackForm: function () {
                if (true) {
                    $("#loading").hide();
                    $("#frmDriverFavorit").hide();
                    $("#frmDriver").show();

                }
                else {
                    return false;
                }
            },
            //---------reciver------------------
            ReciverReturn: function () {
                if (true) {
                    generalCls.SetWizard(1);
                }
                else {
                    return false;
                }
            },
            ReciverNext: function () {
                if (true) {
                    objformhelper.validate.init("frmReciver")
                        .success(function () {
                            $("#loading").show();

                            //       generalCls.GetDocumentById();
                            generalCls.SetWizard(3);
                            //  $("#pelakCombo").val(21);
                            $("#frmpelaq").show();
                            window.scroll(0, 0);
                            $("#loading").hide();
                            FormShippingDocumentationSystemClick.GetCostSettingsForTajmi();


                        })
                        .error(function () {
                            return false;
                        });
                }
                else {
                    return false;
                }
            },
            reciverfavorite: function () {
                $("#receiversearchtext").val("");
                $("#frmReciver").hide();
                $("#frmReciverFavorit").show();
                myDataTableReceiver.ajax.reload();
            },
            AddressSenderfavorite: function () {

                $("#frmmabda").hide();
                $("#frmSenderAddressrFavorit").show();
                myDataTableSenderAddress.ajax.reload();
            },
            AddressReciverfavorite: function () {

                //$("#formmagsad").hide();
                //$("#frmReciverAddressrFavorit").show();
                //myDataTableReciverAddress.ajax.reload();




                $("#formmagsad").hide();
                $("#frmReceiverAddressrFavorit").show();
                myDataTableReciverAddress.ajax.reload();
                /*myDataTableReceiverAddress.ajax.reload();*/
            },
            btnDeleteDetailsReceiver: function () {

                var row = $(this).parents('tr');
                /* generalJS.setSession("keyDoc", myDataTableReceiver.row(row).data()['id']);*/
                idReceiver = myDataTableReceiver.row(row).data()['id'];
                if (true) {
                    FormShippingDocumentationSystemClick.deleteReceiver();

                }
                else {
                    return false;
                }
            },
            deleteReceiver: function () {
                if (true) {
                    $("#loading").show();
                    $.ajax({
                        url: "/Barname/Document/btnDeletePreReceiver",
                        data: {
                            idReceiver: idReceiver,
                        },
                        success: function (success) {
                            //success = JSON.parse(success)
                            $("#loading").hide();

                            if (success.resultCode == 200) {
                                toaster.toast("success", "پیغام سیستم", success.resultMessage)
                                myDataTableReceiver.ajax.reload();
                            }
                            else {

                                toaster.toast("error", "خطا", success.resultMessage)
                            }
                        },
                        error: function (error) {

                            $("#loading").hide();
                            let raw = error.responseText || "";
                            let jsonPart = null;


                            let start = raw.indexOf("{");
                            let end = raw.lastIndexOf("}");

                            if (start !== -1 && end !== -1 && end > start) {
                                let possibleJson = raw.substring(start, end + 1);

                                try {
                                    jsonPart = JSON.parse(possibleJson);
                                } catch (e) {
                                    console.log("JSON parse failed:", e);
                                }
                            }


                            let msg = jsonPart?.resultMessage || jsonPart?.ResultMessage || "خطا در پردازش درخواست";


                            toaster.toast("error", "خطا", msg);

                            if (error.status == 401) {
                                $("#loading").show()
                                window.location = "/Barname/Account/Logout";
                            }

                        }
                    });
                }
                else {
                    return false;
                }
            },
            btneditDeatailReceiver: function () {

                var row = $(this).parents('tr');
                /*generalJS.setSession("keyDoc", myDataTableReceiver.row(row).data()['id']);*/
                idreceiver = myDataTableReceiver.row(row).data()['id'];
                receiverFirstName = myDataTableReceiver.row(row).data()['receiverFirstName'];
                receiverLastName = myDataTableReceiver.row(row).data()['receiverLastName'];
                receiverNationalCode = myDataTableReceiver.row(row).data()['receiverNationalCode'];
                receiverMobile = myDataTableReceiver.row(row).data()['receiverMobile'];
                receiverTelNumber = myDataTableReceiver.row(row).data()['receiverTelNumber'];
                receiverPostalCode = myDataTableReceiver.row(row).data()['receiverPostalCode'];
                if (true) {
                    $("#txtReceiverFirstName").val("");
                    $("#txtReceiverLastName").val("");
                    $("#txtReceiverMobile").val("");
                    $("#txtReceiverNationalCode").val("");
                    $("#txtReceiverTell").val("");
                    $("#txtReceiverPostalCode").val("");
                    //---------------------------------------------
                    $("#txtReceiverFirstNameModal").val(receiverFirstName).trigger("change");
                    $("#txtReceiverLastNameModal").val(receiverLastName).trigger("change");
                    $("#txtReceiverMobileModal").val(receiverMobile).trigger("change");
                    $("#txtReceiverNationalCodeModal").val(receiverNationalCode).trigger("change");
                    $("#txtReceiverTellModal").val(receiverTelNumber).trigger("change");
                    $("#txtReceiverPostalCodeModal").val(receiverPostalCode).trigger("change");
                    $("#modaleditreceiver").modal('show');


                }
                else {
                    return false;
                }
            },
            selectReceiver: function () {
                if (true) {

                    $("#loading").show();
                    var row = $(this).parents('tr');
                    /* generalJS.setSession("keyDoc", myDataTableReceiver.row(row).data()['id']);*/
                    idReceiver = myDataTableReceiver.row(row).data()['id'];
                    var Datas = myDataTableReceiver.row(row).data();
                    var receiverFirstName = Datas.receiverFirstName;
                    var receiverLastName = Datas.receiverLastName;
                    var IsHoghughi = Datas.isCompany;


                    //$("#txtReceiverFirstName").val(myDataTableReceiver.row(row).data()['receiverFirstName']).trigger("change");
                    //$("#txtReceiverOfficeName").val(myDataTableReceiver.row(row).data()['receiverFirstName']).trigger("change");


                    /*  $("#txtReceiverLastName").val(myDataTableReceiver.row(row).data()['receiverLastName']).trigger("change");*/
                    $("#receiverSelectType").val(myDataTableReceiver.row(row).data()['isCompany'] ? 2 : 1).trigger("change"); //نوع بارنامه
                    $("#txtReceiverNationalCode").val(myDataTableReceiver.row(row).data()['receiverNationalCode']).trigger("change");
                    $("#txtReceiverMobile").val(myDataTableReceiver.row(row).data()['receiverMobile']).trigger("change");
                    $("#txtReceiverTell").val(myDataTableReceiver.row(row).data()['receiverTelNumber']).trigger("change");
                    $("#txtReceiverPostalCode").val(myDataTableReceiver.row(row).data()['receiverPostalCode']).trigger("change");
                    if (myDataTableReceiver.row(row).data()['receiverFirstName'] != null) {
                        $("#frmReciver input[name='receiverFirstName']").removeAttr("required");
                        $("#frmReciver input[name='receiverFirstName']").removeAttr("data-fv-notempty-message");
                        $("#frmReciver  input[name='receiverFirstName']").parents().parents().removeClass("has-success has-error");
                        $("#loading").hide();
                    }
                    else {
                        $("input[name='receiverFirstName']").attr("required", "receiverFirstName");
                        $("input[name='receiverFirstName']").attr("data-fv-notempty-message", "وارد کردن مقدار اجباری است");
                    }

                    if (myDataTableReceiver.row(row).data()['receiverLastName'] != null) {
                        $("#frmReciver input[name='receiverLastName']").removeAttr("required");
                        $("#frmReciver input[name='receiverLastName']").removeAttr("data-fv-notempty-message");
                        $("#frmReciver  input[name='receiverLastName']").parents().parents().removeClass("has-success has-error");
                        $("#loading").hide();
                    }
                    else {
                        $("input[name='receiverLastName']").attr("required", "receiverLastName");
                        $("input[name='receiverLastName']").attr("data-fv-notempty-message", "وارد کردن مقدار اجباری است");
                    }
                    $("#loading").hide();
                    $("#frmReciver").show();
                    $("#frmReciverFavorit").hide();

                    if (IsHoghughi == false) {

                        $("#txtReceiverFirstName").val(receiverFirstName).trigger("change");
                        $("#txtReceiverLastName").val(receiverLastName).trigger("change");
                    } else {
                        $("#txtReceiverOfficeName").val(receiverFirstName).trigger("change");

                    }
                }
                else {
                    return false;
                }
            },
            UpdateReceiver: function () {
                if (true) {
                    objformhelper.validate.init("frmmodalreceiver")
                        .success(function () {
                            $("#loading").show();
                            $.ajax({
                                url: "/Account/FormDocumentDetailsRegister.aspx",
                                function: "btnUpdatePreReceiver",
                                data: {

                                    idreceiver: idreceiver,
                                    receiverFullName: $("#txtReceiverFullNameModal").val(),
                                    receiverNationalCode: $("#txtReceiverNationalCodeModal").val(),
                                    receiverMobile: $("#txtReceiverMobileModal").val(),
                                    receiverTell: $("#txtReceiverTellModal").val(),
                                    receiverPostalCode: $("#txtReceiverPostalCodeModal").val(),
                                },
                                success: function (success) {
                                    $("#loading").hide();
                                    if (success.resultCode == 200) {
                                        toaster.toast("success", "پیغام سیستم", success.resultMessage)

                                        myDataTableReceiver.ajax.reload();
                                    }
                                    else {

                                        toaster.toast("error", "پیغام خطا", success.resultMessage)
                                    }
                                },
                                error: function (error) {
                                    $("#loading").hide();
                                    toaster.toast("error", "خطا", error.statusText);

                                }
                            });

                        })
                        .error(function () {
                            return false;
                        });
                }
                else {
                    return false;
                }
            },
            SelectedReceiver: function () {
                if (true) {
                    ddReceiver = $('#ddReceiver option:selected').val();
                    $("#loading").show();
                    if (ddSender != 0) {
                        $.ajax({
                            url: "/Barname/Document/SelectedReceiver",
                            data: { ddReceiver: ddReceiver },
                            success: function (Doc) {

                                $("#loading").hide();
                                $("#txtReceiverFirstName").val(Doc.receiverFirstName).trigger("change");
                                $("#txtReceiverLastName").val(Doc.receiverLastName).trigger("change");
                                $("#txtReceiverMobile").val(Doc.receiverMobile).trigger("change");
                                $("#txtReceiverNationalCode").val(Doc.receiverNationalCode).trigger("change");
                                $("#receiverSelectType").val(Doc.IsCompany).trigger("change");



                                //      $("#txtReceiverTell").val(),
                                //$("#txtReceiverPostalCode").val(),
                            },
                            error: function (error) {
                                $("#loading").hide();
                                toaster.toast("error", "خطا", error.statusText);
                                return false;
                            }
                        });
                    }
                }
                else {
                    return false;
                }
            },
            btnRegPreReceiver: function () {
                if (true) {
                    if ($("#receiverSelectType").val() == 1) {
                        var selectIsCompany = false;

                    } else {
                        var selectIsCompany = true;
                    }
                    objformhelper.validate.init("frmReciver")
                        .success(function () {
                            if (true) {
                                $("#loading").show();
                                $.ajax({
                                    url: "/Barname/Document/btnRegPreReceiver",
                                    data: {
                                        txtReceiverFirstName: $("#txtReceiverFirstName").val() ? $("#txtReceiverFirstName").val() : $("#txtReceiverOfficeName").val(),
                                        txtReceiverLastName: $("#txtReceiverLastName").val() ? $("#txtReceiverLastName").val() : "",
                                        txtReceiverMobile: $("#txtReceiverMobile").val(),
                                        txtReceiverNationalCode: $("#txtReceiverNationalCode").val() ? $("#txtReceiverNationalCode").val() : "",
                                        txtReceiverTell: $("#txtReceiverTell").val(),
                                        txtReceiverPostalCode: $("#txtReceiverPostalCode").val(),
                                        IsCompany: selectIsCompany,
                                    },
                                    success: function (success) {
                                       // success = JSON.parse(success)
                                        $("#loading").hide();
                                        if (success.resultCode == 200) {
                                            toaster.toast("success", "پیغام سیستم", success.resultMessage)
                                        }
                                        else {

                                            toaster.toast("error", "پیغام خطا", success.resultMessage)
                                        }

                                    },
                                    error: function (error) {

                                        $("#loading").hide();
                                        let raw = error.responseText || "";
                                        let jsonPart = null;


                                        let start = raw.indexOf("{");
                                        let end = raw.lastIndexOf("}");

                                        if (start !== -1 && end !== -1 && end > start) {
                                            let possibleJson = raw.substring(start, end + 1);

                                            try {
                                                jsonPart = JSON.parse(possibleJson);
                                            } catch (e) {
                                                console.log("JSON parse failed:", e);
                                            }
                                        }


                                        let msg = jsonPart?.resultMessage || jsonPart?.ResultMessage || "خطا در پردازش درخواست";


                                        toaster.toast("error", "خطا", msg);

                                        if (error.status == 401) {
                                            $("#loading").show()
                                            window.location = "/Barname/Account/Logout";
                                        }

                                    }
                                });
                            }
                            else {
                                return false;
                            }
                        })
                        .error(function () {
                            return false;
                        });
                }
                else {
                    return false;
                }
            },
            receivergridReturn: function () {
                $("#frmReciver").show();
                $("#frmReciverFavorit").hide();

            },
            addresSenderdReturn: function () {

                $("#frmSenderAddressrFavorit").hide();
                $("#frmmabda").show();

            },
            addressReciverReturn: function () {
                $("#frmReceiverAddressrFavorit").hide();
                $("#formmagsad").show();

            },
            //---------Driver and Pelak------------------
            DriverSearch: function () {
                $("#DriverFullName").text('');
                $("#DriverNumberDriverLicense").text('');
                $("#DriverMobile").text('');
                $("#DriverRating").text('');

                if (true) {
                    objformhelper.validate.init("frmDriver")
                        .success(function () {
                            //$("#loading").show();
                            //$.ajax({
                            //    url: "/Barname/Document/DriverSearch",

                            //    data: { txtDriverSearch: $("#txtDriverSearch").val() },
                            //    success: function (result) {
                            //        $("#loading").hide();
                            //        result = JSON.parse(result)
                            //        if (result.resultCode == 200 || result.resultCode == 0) {


                            //            driverMobile = result.obj.mobileNumber;
                            //            if (result.obj.mobileNumber.toString().length > 9) {
                            //                result.obj.mobileNumber = result.obj.mobileNumber.toString().substring(0, 5) + "***" + result.obj.mobileNumber.toString().substring(8, 11);
                            //            }

                            //            $("#ShowDetailsDriver").show();
                            //            firstName = result.obj.firstName;
                            //            LastName = result.obj.lastName
                            //            $("#DriverFullName").val(firstName + " " + LastName);
                            //            LicenseNumber = result.obj.licenseNumber;
                            //            $("#DriverNumberDriverLicense").val(result.obj.driverLicenseId);
                            //            $("#DriverMobile").val(result.obj.mobileNumber);
                            //            $("#DriverRating").val(result.obj.rankName);

                            //            haveCertificate = result.haveBusinessLicense;
                            //            if (result.obj.licenseStatusTitle != null && result.obj.licenseStatusTitle != "") {
                            //                $("#DriverEmploymentlicense").val("دارد");
                            //            }
                            //            else {
                            //                $("#DriverEmploymentlicense").val("ندارد");
                            //            }
                            //            $("#frmpelaq").show();

                            //            DriverSearchv = 1;
                            //        }
                            //        else {
                            //            toaster.toast("error", "خطا", result.resultMessage)

                            //        }

                            //    },
                            //    error: function (error) {
                            //        $("#loading").hide();
                            //        DriverSearchv = 0;
                            //        toaster.toast("error", "خطا", error.statusText);
                            //        return false;
                            //    }
                            //});
                        })

                        .error(function () {

                            return false;
                        });
                }
                else {
                    return false;
                }
            },
            btnDriverFavorit: function () {
                $("#frmDriver").hide();
                $("#frmDriverFavorit").show();
                myDataTableDriver.ajax.reload();
            },
            selectDriver: function () {
                if (true) {
                    $("#loading").show();

                    var row = $(this).parents('tr');
                    /*    generalJS.setSession("keyDoc", myDataTableDriver.row(row).data()['id']);*/
                    idDriver = myDataTableDriver.row(row).data()['id'];

                    $("#txtDriverSearch").val(myDataTableDriver.row(row).data()['nationalCode']).trigger("change");

                    //$("#DriverFullName").text(myDataTableDriver.row(row).data()['fullName']).trigger("change");
                    //$("#DriverNumberDriverLicense").text(myDataTableDriver.row(row).data()['drivingCertificateNumber']).trigger("change");
                    //$("#DriverMobile").text(myDataTableDriver.row(row).data()['mobile']).trigger("change");
                    //$("#DriverRating").text(myDataTableDriver.row(row).data()['rank']).trigger("change");
                    //$("#DriverEmploymentlicense").text(myDataTableDriver.row(row).data()['haveCertificate']).trigger("change");
                    $("#DriverFullName").val('');
                    $("#DriverNumberDriverLicense").val('');
                    $("#DriverMobile").val('');
                    $("#DriverRating").val('');
                    $("#DriverEmploymentlicense").val('');
                    if ($("#DriverEmploymentlicense").val() == "true") {
                        $("#DriverEmploymentlicense").val("دارد").trigger("change");
                    }
                    else {
                        $("#DriverEmploymentlicense").val("ندارد");
                    }
                    $("#loading").hide();
                    $("#frmDriver").show();
                    $("#frmDriverFavorit").hide();
                    //$("#frmpelaq").show();
                    //$("#ThirdPartyInsurance").val('');
                    // $("#Activitylicense").val('');
                    // $("#CapacityFrom").val('');
                    // $("#CapacityTo").val('');
                    // $("#TypeofLoader").val('');
                    $("#DriverEmploymentlicense").val('');
                    /*  $("#btnShowDetailsDriver").click()*/
                    //FormShippingDocumentationSystemClick.DriverSearch();

                }
                else {
                    return false;
                }
            },
            btnDeleteDetailsDriver: function () {

                if (true) {
                    var row = $(this).parents('tr');
                    idDriver = myDataTableDriver.row(row).data()['id'];
                    $("#loading").show();
                    $.ajax({
                        url: "/Barname/Document/btnDeleteDriver",
                        data: {
                            idDriver: idDriver,
                        },
                        success: function (success) {
                            $("#loading").hide();
                            //success = JSON.parse(success)
                            if (success.resultCode == 200) {
                                toaster.toast("success", "پیغام سیستم", success.resultMessage)
                                myDataTableDriver.ajax.reload();
                            }
                            else {



                                toaster.toast("error", "پیغام خطا", success.resultMessage)

                            }
                        },
                        error: function (error) {

                            $("#loading").hide();
                            let raw = error.responseText || "";
                            let jsonPart = null;


                            let start = raw.indexOf("{");
                            let end = raw.lastIndexOf("}");

                            if (start !== -1 && end !== -1 && end > start) {
                                let possibleJson = raw.substring(start, end + 1);

                                try {
                                    jsonPart = JSON.parse(possibleJson);
                                } catch (e) {
                                    console.log("JSON parse failed:", e);
                                }
                            }


                            let msg = jsonPart?.resultMessage || jsonPart?.ResultMessage || "خطا در پردازش درخواست";


                            toaster.toast("error", "خطا", msg);

                            if (error.status == 401) {
                                $("#loading").show()
                                window.location = "/Barname/Account/Logout";
                            }

                        }
                    });
                }
                else {
                    return false;
                }
            },
            btnRegDriver: function () {
                btnRegDriver = 0;
                FormShippingDocumentationSystemClick.DriverSearchbtnRegDriver();

            },
            DriverSearchbtnRegDriver: function () {
                $("#DriverFullName").val('');
                $("#DriverNumberDriverLicense").val('');
                $("#DriverMobile").val('');
                $("#DriverRating").val('');
                if (true) {
                    objformhelper.validate.init("frmDriver")
                        .success(function () {
                            $("#loading").show();
                            $.ajax({
                                url: "/Barname/Document/DriverSearch",
                                data: { txtDriverSearch: $("#txtDriverSearch").val() },
                                success: function (result) {
                                    $("#loading").hide();
                                    result = JSON.parse(result)
                                    if (result.resultCode == 200 || result.resultCode == 0) {

                                        ;
                                        driverMobile = result.obj.mobileNumber;
                                        if (result.obj.mobileNumber.toString().length > 9) {
                                            result.obj.mobileNumber = result.obj.mobileNumber.toString().substring(0, 5) + "***" + result.obj.mobileNumber.toString().substring(8, 11);
                                        }

                                        $("#ShowDetailsDriver").show();
                                        firstName = result.obj.firstName;
                                        LastName = result.obj.lastName
                                        $("#DriverFullName").val(firstName + " " + LastName);
                                        LicenseNumber = result.obj.licenseNumber;
                                        $("#DriverNumberDriverLicense").val(result.obj.driverLicenseId);
                                        $("#DriverMobile").val(result.obj.mobileNumber);
                                        $("#DriverRating").val(result.obj.rankName);

                                        haveCertificate = result.haveBusinessLicense;
                                        if (result.obj.licenseStatusTitle != null && result.obj.licenseStatusTitle != "") {
                                            $("#DriverEmploymentlicense").val("دارد");
                                        }
                                        else {
                                            $("#DriverEmploymentlicense").val("ندارد");
                                        }
                                        $("#frmpelaq").show();

                                        DriverSearchv = 1;
                                        btnRegDriver = 1;
                                        FormShippingDocumentationSystemClick.btnRegDriverFunction();
                                    }
                                    else {
                                        toaster.toast("error", "خطا", result.resultMessage)

                                    }

                                    //$('html, body').animate({
                                    //    scrollTop: $(".up").offset().top
                                    //}, 1500);
                                    //       generalCls.GetDocumentById();
                                },
                                error: function (error) {
                                    $("#loading").hide();

                                    toaster.toast("error", "خطا", error.statusText);
                                    return false;
                                }
                            });
                        })

                        .error(function () {
                            return false;
                        });
                }
                else {
                    return false;
                }
            },
            btnRegDriverFunction: function () {
                if (true) {

                    if ($("#DriverFullName").val().length == 0)
                        FormShippingDocumentationSystemClick.DriverSearch();

                    setTimeout(function () {
                        objformhelper.validate.init("frmDriver")
                            .success(function () {
                                $("#loading").show();
                                $.ajax({
                                    url: "/Barname/Document/PreDriverInsert",
                                    data: {
                                        submitterId: 0,
                                        isSelected: false,
                                        fullName: $("#DriverFullName").val(),
                                        nationalCode: $("#txtDriverSearch").val(),
                                        drivingCertificateNumber: $("#DriverNumberDriverLicense").val(),
                                        mobile: driverMobile,
                                        rank: $("#DriverRating").val(),
                                        haveCertificate: haveCertificate,

                                    },
                                    success: function (success) {
                                        $("#loading").hide();
                                        //success = JSON.parse(success);
                                        if (success.resultCode == 200) {

                                            toaster.toast("success", "پیغام سیستم", success.resultMessage)
                                        }
                                        else {

                                            toaster.toast("error", "پیغام خطا", success.resultMessage)
                                        }
                                        //isSelected= false,
                                    },

                                    error: function (error) {

                                        $("#loading").hide();
                                        let raw = error.responseText || "";
                                        let jsonPart = null;


                                        let start = raw.indexOf("{");
                                        let end = raw.lastIndexOf("}");

                                        if (start !== -1 && end !== -1 && end > start) {
                                            let possibleJson = raw.substring(start, end + 1);

                                            try {
                                                jsonPart = JSON.parse(possibleJson);
                                            } catch (e) {
                                                console.log("JSON parse failed:", e);
                                            }
                                        }


                                        let msg = jsonPart?.resultMessage || jsonPart?.ResultMessage || "خطا در پردازش درخواست";


                                        toaster.toast("error", "خطا", msg);

                                        if (error.status == 401) {
                                            $("#loading").show()
                                            window.location = "/Barname/Account/Logout";
                                        }

                                    }
                                });
                            })
                            .error(function () {
                                return false;
                            });

                    }, 2000);

                }
                else {
                    return false;
                }
            },
            drivergridReturn: function () {
                $("#frmDriver").show();
                $("#frmDriverFavorit").hide();

            },
            getPelakType: function () {

                $("#pelakTypeCombo").val("");
                $("#pelakAzadFarsiNumber").val("");
                $("#pelakAzadLatinNumber").val("");
                $("#pelakIrNum").val("");
                $("#pelakCombo").val("");
                $("#pelakCenter").val("");
                $("#pelakFirst").val("");
                $("#pelakReq").val("");
                $("#pelakAzadFarsiNumber3").val("");
                $("#pelakAzadLatinNumber3").val("");

                var pelaktype = $("#frmpelaq input[name='pelakIsAzad']:checked").val();

                switch (pelaktype) {
                    case "1":
                        FormShippingDocumentationSystemClick.changePelakAzadCombo();
                        $(".plak").parent("div").addClass("hidden");
                        $("#pelakazad").prop('checked', true);
                        $("#pelakmeli").prop('checked', false);

                        break;
                    case "2":
                        $(".plak").parent("div").removeClass("hidden");
                        $("#pelakmeli").prop('checked', true);
                        $("#pelakazad").prop('checked', false);
                        break;
                }
            },
            changePelakAzadCombo: function () {
                ;
                //var pelakTypeCombo = $("#pelakTypeCombo").val();

                //if (pelakTypeCombo == "") {
                //    $("#pelakAzadbox").addClass("hidden");
                //}
                //else {
                //    $("#pelakAzadbox").removeClass("hidden");
                //}

                switch (pelakTypeCombo) {
                    case "7":
                        $("#imgPelakAzad1").prop("src", "../img/pelak/Aras2.png");
                        break;
                    case "1":
                        $("#imgPelakAzad1").prop("src", "../img/pelak/Arvand.png");
                        break;
                    case "2":
                        $("#imgPelakAzad1").prop("src", "../img/pelak/Anzali.png");
                        break;
                    case "3":
                        $("#imgPelakAzad1").prop("src", "../img/pelak/Chabahar.png");
                        break;
                    case "4":
                        $("#imgPelakAzad1").prop("src", "../img/pelak/Qeshm.png");
                        break;
                    case "5":
                        $("#imgPelakAzad1").prop("src", "../img/pelak/kish.png");
                        break;
                    case "6":
                        $("#imgPelakAzad1").prop("src", "../img/pelak/MAKU.png");
                        break;
                }
            },

            PlaqueSearch: function () {
                if (!CheckPelakInput()) {
                    return false
                }
                $("#ThirdPartyInsurance").val('');
                $("#Activitylicense").val('');
                $("#CapacityFrom").val('');
                $("#CapacityTo").val('');
                $("#TypeofLoader").val('');
                if (true) {

                    var pelaktype = $("input[name='pelakIsAzad']:checked").val();

                    switch (pelaktype) {
                        case "1":
                            {

                                selectpelak = 0;
                                t3 = "";
                                t4 = "";
                                rqsSecondThreeNo = "";
                                rqsCharacterNo = $("#pelakAzadFarsiNumber3").val();
                                rqsFirstTwoNo = $("input[id='pelakAzadFarsiNumber']").val();
                                rqsIRTwoNo = $("select[id='pelakTypeCombo'] option:selected").val();
                                var regexStr = "";
                                var len = $("input[id='pelakAzadFarsiNumber']").val().length;
                                var val = $("input[id='pelakAzadFarsiNumber']").val();

                                if (len !== 5) {
                                    $("#pazad").text("  پلاک وارد شده صحیح نمی باشد پلاک را به صورت کامل وارد نمایید");
                                }
                                else {
                                    var validm = /^[0-9]+$/;
                                    if (validm.test(val)) {
                                        $("#pazad").text("");
                                        selectpelak = 1;
                                        if ($("select[id='pelakTypeCombo'] option:selected").val() == "") {
                                            $("#pazad").text(" پلاک وارد شده صحیح نمی باشد شهر مورد نظر را انتخاب نمایید ");
                                        }
                                        else {
                                            $("#pazad").text("");
                                        }
                                    }
                                    else {
                                        $("#pazad").text(" پلاک وارد شده صحیح نمی باشد پلاک را به صورت کامل وارد نمایید");
                                        selectpelak = 0;
                                    }
                                }


                                truckTagType = true;
                                t2 = $("input[id='pelakAzadFarsiNumber']").val();
                                t3 = $("input[id='pelakAzadFarsiNumber3']").val();
                                t1 = $("select[id='pelakTypeCombo'] option:selected").val();

                                break;
                            }
                        case "2":
                            {
                                truckTagType = false;
                                selectpelak = 0;
                                rqsIRTwoNo = $("input[id='pelakIrNum']").val();
                                rqsFirstTwoNo = $("input[name='pelakFirst']").val();
                                rqsCharacterNo = $("select[id='pelakCombo'] option:selected").val();
                                rqsSecondThreeNo = $("input[id='pelakCenter']").val();




                                var lenIR = $("input[id='pelakIrNum']").val().length;
                                var valIR = $("input[id='pelakIrNum']").val();

                                var lenCenter = $("input[id='pelakCenter']").val().length;
                                var valCenter = $("input[id='pelakCenter']").val();

                                var lenFirst = $("input[name='pelakFirst']").val().length;
                                var valFirst = $("input[name='pelakFirst']").val();



                                var selectadi = 0;

                                ////////////////////////////////////////////
                                if (lenIR !== 2) {
                                    selectadi = 1;
                                }
                                else {
                                    var validm = /^[0-9]+$/;
                                    if (validm.test(valIR)) {
                                        selectadi = 0;
                                        selectpelak = 1;
                                        if ($("select[id='pelakCombo'] option:selected").val() == "") {
                                            selectadi = 1;
                                        }
                                        else {
                                            selectadi = 0;
                                        }
                                        //////////////////////////////////////////////////////
                                        if (lenFirst !== 2) {
                                            selectadi = 1;
                                        }
                                        else {
                                            var validm = /^[0-9]+$/;
                                            if (validm.test(valFirst)) {
                                                selectadi = 0;
                                                selectpelak = 1;
                                                if ($("select[id='pelakCombo'] option:selected").val() == "") {
                                                    selectadi = 1;
                                                }
                                                else {
                                                    selectadi = 0;
                                                }
                                                //////////////////////////////////////////////
                                                if (lenCenter !== 3) {
                                                    selectadi = 1;
                                                }
                                                else {
                                                    var validm = /^[0-9]+$/;
                                                    if (validm.test(valCenter)) {
                                                        selectadi = 0;
                                                        selectpelak = 1;
                                                        if ($("select[id='pelakCombo'] option:selected").val() == "") {
                                                            selectadi = 1;
                                                        }
                                                        else {
                                                            selectadi = 0;
                                                        }
                                                    }
                                                    else {
                                                        selectadi = 1;
                                                        selectpelak = 0;
                                                    }
                                                }
                                            }
                                            else {
                                                selectadi = 1;
                                                selectpelak = 0;
                                            }
                                        }
                                    }
                                    else {
                                        selectadi = 1;
                                        selectpelak = 0;
                                    }
                                }
                                if (selectadi == 1) {
                                    selectpelak = 0;
                                    $("#pelakReq").text("پلاک وارد شده صحیح نمی باشد");
                                } else {
                                    selectpelak = 1;
                                    $("#pelakReq").text("");
                                }
                                /////////////////////////////////////////////////////////


                                if (rqsSecondThreeNo == "") {
                                    rqsCharacterNo = "";
                                    rqsFirstTwoNo = "";
                                }
                                truckTagType = false;
                                t1 = $("input[id='pelakIrNum']").val();
                                t2 = $("input[name='pelakFirst']").val();
                                t3 = $("select[id='pelakCombo'] option:selected").val();
                                t4 = $("input[id='pelakCenter']").val();
                                break;
                            }
                    }
                    $("#loading").show();
                    // FormShippingDocumentationSystemClick.getPelakType2();
                    // objformhelper.validate.init("frmpelaq")
                    //.success(function () {

                    if (selectpelak == 1) {
                        pelakv = 1;
                        //$.ajax({
                        //    url: "/Barname/Document/PlaqueSearch",
                        //    data: {
                        //        t1: t1,
                        //        t2: t2,
                        //        t3: t3,
                        //        t4: t4,
                        //    },
                        //    success: function (result) {


                        //        result = JSON.parse(result)
                        //        $("#loading").hide();
                        //        if (result.resultCode == 200) {
                        //            result = result.obj
                        //            pelakv = 0;
                        //            rqsIRTwoNo = 0;
                        //            rqsFirstTwoNo = 0;
                        //            rqsCharacterNo = 0;
                        //            rqsSecondThreeNo = 0;
                        //            $("#CapacityFrom").val(result.capacityFrom);
                        //            $("#CapacityTo").val(result.capacityTo);
                        //            fuelType = result.fuelType;

                        //            $("#TypeofLoader").val(result.truckTypeName);
                        //            havelicense = result.haveLicense;

                        //            have3rd = result.have3rdInsurance;
                        //            if (result.haveLicense == true) {
                        //                $("#Activitylicense").val("دارد");
                        //            }
                        //            else {
                        //                $("#Activitylicense").val("ندارد");
                        //            }
                        //            if (result.have3rdInsurance == true) {
                        //                $("#ThirdPartyInsurance").val("دارد");
                        //            }
                        //            else {
                        //                $("#ThirdPartyInsurance").val("ندارد");
                        //            }
                        //        }
                        //        else {
                        //            toaster.toast("error", "خطا", result.resultMessage)
                        //        }

                        //    },
                        //    error: function (error) {
                        //        $("#loading").hide();
                        //        toaster.toast("error", "خطا", error)
                        //        pelakv = 1;
                        //        $("#CapacityFrom").val('');
                        //        $("#CapacityTo").val('');
                        //        $("#TypeofLoader").val('');
                        //        $("#Activitylicense").val('');
                        //        $("#ThirdPartyInsurance").val('');


                        //        return false;
                        //    }
                        //});
                    }
                    else {

                        $("#loading").hide();
                    }
                    //})
                    //.error(function () {
                    //    return false;
                    //});

                }
                else {
                    return false;
                }
                //})
                //.error(function () {
                //    return false;
                //});
                //  }, 3000)

            },
            //PlaqueSearchTajmi: function () {

            //    $("#ThirdPartyInsuranceTajmi").text('');
            //    $("#ActivitylicenseTajmi").text('');
            //    $("#CapacityTajmi").text('');
            //    $("#TypeofLoaderTajmi").text('');
            //    if (true) {

            //        var pelaktype = $("#frmpelaq input[name='pelakIsAzad']:checked").val();
            //        switch (pelaktype) {
            //            case "1":
            //                {
            //                    selectpelak = 0;
            //                    t3 = "";
            //                    t4 = "";
            //                    rqsSecondThreeNo = "";
            //                    rqsCharacterNo = $("#pelakAzadFarsiNumber3").val();
            //                    rqsFirstTwoNo = $("input[id='pelakAzadFarsiNumber']").val();
            //                    rqsIRTwoNo = $("select[id='pelakTypeCombo'] option:selected").val();
            //                    var regexStr = "";
            //                    var len = $("input[id='pelakAzadFarsiNumber']").val().length;
            //                    var val = $("input[id='pelakAzadFarsiNumber']").val();

            //                    if (len !== 5) {
            //                        $("#pazad").text("  پلاک وارد شده صحیح نمی باشد پلاک را به صورت کامل وارد نمایید");
            //                    }
            //                    else {
            //                        var validm = /^[0-9]+$/;
            //                        if (validm.test(val)) {
            //                            $("#pazad").text("");
            //                            selectpelak = 1;
            //                            if ($("select[id='pelakTypeCombo'] option:selected").val() == "") {
            //                                $("#pazad").text(" پلاک وارد شده صحیح نمی باشد شهر مورد نظر را انتخاب نمایید ");
            //                            }
            //                            else {
            //                                $("#pazad").text("");
            //                            }
            //                        }
            //                        else {
            //                            $("#pazad").text(" پلاک وارد شده صحیح نمی باشد پلاک را به صورت کامل وارد نمایید");
            //                            selectpelak = 0;
            //                        }
            //                    }


            //                    truckTagType = true;
            //                    t2 = $("input[id='pelakAzadFarsiNumber']").val();
            //                    t1 = $("select[id='pelakTypeCombo'] option:selected").val();
            //                    break;
            //                }
            //            case "2":
            //                {
            //                    truckTagType = false;
            //                    selectpelak = 0;
            //                    rqsIRTwoNo = $("input[id='pelakIrNum']").val();
            //                    rqsFirstTwoNo = $("input[name='pelakFirst']").val();
            //                    rqsCharacterNo = $("select[id='pelakCombo'] option:selected").val();
            //                    rqsSecondThreeNo = $("input[id='pelakCenter']").val();

            //                    var lenIR = $("input[id='pelakIrNum']").val().length;
            //                    var valIR = $("input[id='pelakIrNum']").val();

            //                    var lenCenter = $("input[id='pelakCenter']").val().length;
            //                    var valCenter = $("input[id='pelakCenter']").val();

            //                    var lenFirst = $("input[name='pelakFirst']").val().length;
            //                    var valFirst = $("input[name='pelakFirst']").val();

            //                    var selectadi = 0;

            //                    ////////////////////////////////////////////
            //                    if (lenIR !== 2) {
            //                        selectadi = 1;
            //                    }
            //                    else {
            //                        var validm = /^[0-9]+$/;
            //                        if (validm.test(valIR)) {
            //                            selectadi = 0;
            //                            selectpelak = 1;
            //                            if ($("select[id='pelakCombo'] option:selected").val() == "") {
            //                                selectadi = 1;
            //                            }
            //                            else {
            //                                selectadi = 0;
            //                            }
            //                            //////////////////////////////////////////////////////
            //                            if (lenFirst !== 2) {
            //                                selectadi = 1;
            //                            }
            //                            else {
            //                                var validm = /^[0-9]+$/;
            //                                if (validm.test(valFirst)) {
            //                                    selectadi = 0;
            //                                    selectpelak = 1;
            //                                    if ($("select[id='pelakCombo'] option:selected").val() == "") {
            //                                        selectadi = 1;
            //                                    }
            //                                    else {
            //                                        selectadi = 0;
            //                                    }
            //                                    //////////////////////////////////////////////
            //                                    if (lenCenter !== 3) {
            //                                        selectadi = 1;
            //                                    }
            //                                    else {
            //                                        var validm = /^[0-9]+$/;
            //                                        if (validm.test(valCenter)) {
            //                                            selectadi = 0;
            //                                            selectpelak = 1;
            //                                            if ($("select[id='pelakCombo'] option:selected").val() == "") {
            //                                                selectadi = 1;
            //                                            }
            //                                            else {
            //                                                selectadi = 0;
            //                                            }
            //                                        }
            //                                        else {
            //                                            selectadi = 1;
            //                                            selectpelak = 0;
            //                                        }
            //                                    }
            //                                }
            //                                else {
            //                                    selectadi = 1;
            //                                    selectpelak = 0;
            //                                }
            //                            }
            //                        }
            //                        else {
            //                            selectadi = 1;
            //                            selectpelak = 0;
            //                        }
            //                    }
            //                    if (selectadi == 1) {
            //                        selectpelak = 0;
            //                        $("#pelakReq").text("پلاک وارد شده صحیح نمی باشد");
            //                    } else {
            //                        selectpelak = 1;
            //                        $("#pelakReq").text("");
            //                    }
            //                    /////////////////////////////////////////////////////////

            //                    break;

            //                    if (rqsSecondThreeNo == "") {
            //                        rqsCharacterNo = "";
            //                        rqsFirstTwoNo = "";
            //                    }
            //                    truckTagType = false;
            //                    t1 = $("input[id='pelakIrNum']").val();
            //                    t2 = $("input[name='pelakFirst']").val();
            //                    t3 = $("select[id='pelakCombo'] option:selected").val();
            //                    t4 = $("input[id='pelakCenter']").val();
            //                    break;
            //                }
            //        }
            //        $("#loading").show();
            //        // FormShippingDocumentationSystemClick.getPelakType2();
            //        // objformhelper.validate.init("frmpelaq")
            //        //.success(function () {

            //        if (selectpelak == 1) {
            //            pelakv = 1;
            //            $.ajax({
            //                url: "/Account/FormDocumentDetailsRegister.aspx",
            //                function: "PlaqueSearch",
            //                data: {
            //                    t1: rqsIRTwoNo,
            //                    t2: rqsFirstTwoNo,
            //                    t3: rqsCharacterNo,
            //                    t4: rqsSecondThreeNo,
            //                },
            //                success: function (result) {
            //                    $("#loading").hide();
            //                    pelakv = 0;
            //                    rqsIRTwoNo = 0;
            //                    rqsFirstTwoNo = 0;
            //                    rqsCharacterNo = 0;
            //                    rqsSecondThreeNo = 0;
            //                    $("#CapacityFrom").text(result.capacity);
            //                    fuelType = result.fuelType;

            //                    $("#TypeofLoader").text(result.truckTypeName);
            //                    havelicense = result.haveLicense;

            //                    have3rd = result.have3rdInsurance;
            //                    if (result.haveLicense == true) {
            //                        $("#Activitylicense").text("دارد");
            //                    }
            //                    else {
            //                        $("#Activitylicense").text("ندارد");
            //                    }
            //                    if (result.have3rdInsurance == true) {
            //                        $("#ThirdPartyInsurance").text("دارد");
            //                    }
            //                    else {
            //                        $("#ThirdPartyInsurance").text("ندارد");
            //                    }
            //                },
            //                error: function (error) {
            //                    $("#loading").hide();
            //                    toaster.toast("error", "خطا", error.statusText);
            //                    pelakv = 1;
            //                    $("#CapacityFrom").text('');
            //                    $("#TypeofLoader").text('');
            //                    $("#Activitylicense").text('');
            //                    $("#ThirdPartyInsurance").text('');


            //                    return false;
            //                }
            //            });
            //        }
            //        else {

            //            $("#loading").hide();
            //        }
            //        //})
            //        //.error(function () {
            //        //    return false;
            //        //});

            //    }
            //    else {
            //        return false;
            //    }
            //    //})
            //    //.error(function () {
            //    //    return false;
            //    //});
            //    //  }, 3000)

            //},
            //getPelakType: function () {
            //  
            //    $("#pelakIrNum1, #pelakCombo1, #pelakCenter1, #pelakFirst1, #pelakReq1, #pelakAzadLatinNumber1, #pelakAzadFarsiNumber1, #pelakTypeCombo1").val("");
            //    $("#pelakTypeCombo1").parent("div").removeClass("has-success");
            //    $("#pelakReqDiv").removeClass("has-success");
            //    var inputs = $('#validBox1').find("input,select");
            //    $.each(inputs, function () {
            //        if ($(this).attr("required")) {
            //            $(this).removeAttr("required");
            //            $("#frmpelaq").formValidation('removeField', $(this));
            //        }
            //        if ($(this).attr("minlength")) {
            //            $(this).removeAttr("minlength");
            //            $("#frmpelaq").formValidation('removeField', $(this));
            //        }
            //        if ($(this).attr("maxlength")) {
            //            $(this).removeAttr("maxlength");
            //            $("#frmpelaq").formValidation('removeField', $(this));
            //        }
            //        if ($(this).attr("data-fv-onlynumber")) {
            //            $(this).removeAttr("data-fv-onlynumber");
            //            $("#frmpelaq").formValidation('removeField', $(this));
            //        }
            //    });
            //    //objformhelper.init("frmpelaq");
            //    var pelaktype = $("#frmpelaq input[name='pelakType']:checked").val();
            //    switch (pelaktype) {
            //        case "1": {
            //          
            //            FormShippingDocumentationSystemClick.changePelakAzadCombo();
            //            //FormShippingDocumentationSystemClick.GetAllFreeZoneList();
            //            //$("#azadPelakType1").removeClass("hidden");
            //            ////$("#azadPelakType2").addClass("hidden");
            //            //$(".pelak").parent("div").addClass("hidden");
            //            $("#azadPelakType2").hide();
            //            $("#azadPelakType1").show();
            //            $("#frmpelaq select[name='pelakTypeCombo1']").attr("required", "required");
            //            $("#frmpelaq input[name='pelakAzadFarsiNumber1']").attr("required", "required");
            //            $("#frmpelaq input[name='pelakAzadLatinNumber1']").attr("required", "required");
            //            $("#frmpelaq input[name='pelakAzadFarsiNumber1']").attr("minlength", "5");
            //            $("#frmpelaq input[name='pelakAzadFarsiNumber1']").attr("maxlength", "5");
            //            $("#frmpelaq input[name='pelakAzadLatinNumber1']").attr("maxlength", "5");
            //            $("#frmpelaq input[name='pelakAzadLatinNumber1']").attr("minlength", "5");
            //            $("#frmpelaq input[name='pelakAzadLatinNumber1']").attr("data-fv-onlynumber", true);
            //            $("#frmpelaq input[name='pelakAzadFarsiNumber1']").attr("data-fv-onlynumber", true);
            //            $("#frmpelaq").formValidation('addField', $("#frmpelaq select[name='pelakTypeCombo1']"));
            //            $("#frmpelaq").formValidation('addField', $("#frmpelaq input[name='pelakAzadFarsiNumber1']"));
            //            $("#frmpelaq").formValidation('addField', $("#frmpelaq input[name='pelakAzadLatinNumber1']"));
            //            //objformhelper.init("frmpelaq");
            //        }
            //            break;
            //        case "2": {
            //          
            //            //$("#azadPelakType1").addClass("hidden");
            //            ////$("#azadPelakType2").removeClass("hidden");
            //            //$(".pelak").parent("div").removeClass("hidden");
            //            ////$("adi").addClass("hidden");
            //            $("#azadPelakType1").hide();
            //            $("#azadPelakType2").show();
            //            $("#frmpelaq input[name='pelakReq']").attr("required", "required");
            //            $("#frmpelaq input[name='pelakIrNum1']").attr("data-fv-onlynumber", true);
            //            $("#frmpelaq input[name='pelakCenter1']").attr("data-fv-onlynumber", true);
            //            $("#frmpelaq input[name='pelakFirst1']").attr("data-fv-onlynumber", true);
            //            $("#frmpelaq input[name='pelakIrNum1']").attr("minlength", "2");
            //            $("#frmpelaq input[name='pelakIrNum1']").attr("maxlength", "2");
            //            $("#frmpelaq input[name='pelakCenter1']").attr("maxlength", "3");
            //            $("#frmpelaq input[name='pelakCenter1']").attr("minlength", "3");
            //            $("#frmpelaq input[name='pelakFirst1']").attr("maxlength", "2");
            //            $("#frmpelaq input[name='pelakFirst1']").attr("minlength", "2");
            //            $("#frmpelaq").formValidation('addField', $("#frmpelaq input[name='pelakIrNum1']"));
            //            $("#frmpelaq").formValidation('addField', $("#frmpelaq input[name='pelakCenter1']"));
            //            $("#frmpelaq").formValidation('addField', $("#frmpelaq input[name='pelakFirst1']"));
            //            $("#frmpelaq").formValidation('addField', $("#frmpelaq input[name='pelakReq']"));
            //            $("#frmpelaq").formValidation('addField', $("#frmpelaq select[name='pelakCombo1']"));
            //            //objformhelper.init("frmpelaq");
            //        }
            //    }
            //},
            //changePelakAzadCombo: function () {
            //  
            //    var pelakTypeCombo = $("select[name='pelakTypeCombo1'] option:selected").val();
            //    if (pelakTypeCombo == "") {
            //        $("#pelakAzadbox1").addClass("hidden");
            //    }
            //    else {
            //        $("#pelakAzadbox1").removeClass("hidden");
            //    }
            //  
            //    switch (pelakTypeCombo) {
            //        case "0":
            //            $("#imgPelakAzad1").prop("src", "../img/pelak/Aras2.png");
            //            break;
            //        case "1":
            //            $("#imgPelakAzad1").prop("src", "../img/pelak/Arvand.png");
            //            break;
            //        case "2":
            //            $("#imgPelakAzad1").prop("src", "../img/pelak/Anzali.png");
            //            break;
            //        case "3":
            //            $("#imgPelakAzad1").prop("src", "../img/pelak/Chabahar.png");
            //            break;
            //        case "4":
            //            $("#imgPelakAzad1").prop("src", "../img/pelak/Qeshm.png");
            //            break;
            //        case "5":
            //            $("#imgPelakAzad1").prop("src", "../img/pelak/kish.png");
            //            break;
            //        case "6":
            //            $("#imgPelakAzad1").prop("src", "../img/pelak/MAKU.png");
            //            break;
            //    }
            //},
            btnPelaqFavorit: function () {

                $("#pelakinvalidtotal").hide();
                $("#frmpelaq").hide();
                $("#frmpelakFavorit").show();
                myDataTablePelak.ajax.reload();
            },
            selectPelak: function () {
                if (true) {

                    var row = $(this).parents('tr');

                    if ((myDataTablePelak.row(row).data()['t4'] == null)) {//.attr("checked", "checked")

                        $("#azadPelakType").prop('checked', true).trigger("click");
                        $("#BoxSelect").prop('checked', false);

                        //$("#frmpelaq input[name='pelakazad'][value='1']").trigger("click");//.trigger("click");


                    } else {

                        $("#azadPelakType").prop('checked', false);
                        $("#BoxSelect").prop('checked', true).trigger("click");

                        //$("#frmpelaq input[name='pelakmeli'][value='2']").trigger("click");//.trigger("click");

                    }

                    $("#loading").show();
                    pelakv = 0;
                    /* generalJS.setSession("keyDoc", myDataTablePelak.row(row).data()['Id']);*/
                    idPelak = myDataTablePelak.row(row).data()['Id'];

                    $("#pelakTypeCombo").val(myDataTablePelak.row(row).data()['freeZoneCode']);
                    $("#pelakAzadFarsiNumber").val(myDataTablePelak.row(row).data()['freeZoneNo']);
                    $("#pelakAzadLatinNumber").val(myDataTablePelak.row(row).data()['freeZoneNo']);
                    if ((myDataTablePelak.row(row).data()['t4'] == null)) {
                        $("#pelakAzadFarsiNumber3").val(myDataTablePelak.row(row).data()['t3']);
                        $("#pelakAzadLatinNumber3").val(myDataTablePelak.row(row).data()['t3']);

                    }


                    $("#pelakIrNum").val(myDataTablePelak.row(row).data()['t1']);
                    $("#pelakCenter").val(myDataTablePelak.row(row).data()['t4']);
                    $("#pelakCombo").val(myDataTablePelak.row(row).data()['t3']);
                    $("#pelakFirst").val(myDataTablePelak.row(row).data()['t2']);
                    $("#pelakReq").text("");
                    $("#pazad").text("");
                    FormShippingDocumentationSystemClick.changePelakAzadCombo();
                    if ((myDataTablePelak.row(row).data()['t4'] == null)) {

                        $("#AzadColor").css("color", "#fffff");
                        $("#AzadBackground").css("background-color", "#3bacff");
                        $("#AdiColor").css("color", "#007e90");
                        $("#AdiBackground").css("background-color", "#fffff");
                        //$("#frmpelaq input[name='pelakType']:checked").val(1)
                        $("#pelakIrNum").val('');
                        $("#pelakCenter").val('');
                        $("#pelakCombo").val('');
                        $("#pelakFirst").val('');
                        $("#frmpelaq input[name='pelakIsAzad']:checked").val(1);
                        $("#pelakAzadbox").removeClass("hidden");
                    }
                    else {

                        $("#AdiColor").css("color", "#fffff");
                        $("#AdiBackground").css("background-color", "#3bacff");
                        $("#AzadColor").css("color", "#007e90");
                        $("#AzadBackground").css("background-color", "#fffff");
                        $("#pelakAzadFarsiNumber").val('');
                        $("#pelakAzadLatinNumber").val('');
                        $("#frmpelaq input[name='pelakIsAzad']:checked").val(2);
                    }

                    $("#loading").hide();
                    $("#frmpelaq").show();
                    $("#frmpelakFavorit").hide();

                    /*$("#btnShowDetailspelaq").click()*/
                }
                else {
                    return false;
                }
            },
            btnDeletePelak: function () {
                if (true) {

                    var row = $(this).parents('tr');
                    /*  generalJS.setSession("keyDoc", myDataTablePelak.row(row).data()['id']);*/
                    idPelak = myDataTablePelak.row(row).data()['id'];

                    $("#loading").show();
                    $.ajax({
                        url: "/Barname/Document/btnDeletePelak",
                        data: {
                            truckId: idPelak,
                        },
                        success: function (success) {
                            //success = JSON.parse(success)
                            $("#loading").hide();

                            if (success.resultCode == 200) {

                                toaster.toast("success", "پیغام سیستم", success.resultMessage)
                                myDataTablePelak.ajax.reload();
                            }
                            else {
                                toaster.toast("error", "پیغام خطا", success.resultMessage)
                            }
                        },
                        error: function (error) {

                            $("#loading").hide();
                            let raw = error.responseText || "";
                            let jsonPart = null;


                            let start = raw.indexOf("{");
                            let end = raw.lastIndexOf("}");

                            if (start !== -1 && end !== -1 && end > start) {
                                let possibleJson = raw.substring(start, end + 1);

                                try {
                                    jsonPart = JSON.parse(possibleJson);
                                } catch (e) {
                                    console.log("JSON parse failed:", e);
                                }
                            }


                            let msg = jsonPart?.resultMessage || jsonPart?.ResultMessage || "خطا در پردازش درخواست";


                            toaster.toast("error", "خطا", msg);

                            if (error.status == 401) {
                                $("#loading").show()
                                window.location = "/Barname/Account/Logout";
                            }

                        }
                    });
                }
                else {
                    return false;
                }
            },
            btnRegPelak: function () {
                if (!CheckPelakInput()) {
                    return false
                }
                btnRegPelak = 0;
                FormShippingDocumentationSystemClick.PlaqueSearchForbtnRegPelak();

            },
            btnRegPelakFunction: function () {
                if (true) {
                    var pelaktype = $("input[name='pelakIsAzad']:checked").val();
                    switch (pelaktype) {
                        case "1":
                            {

                                selectpelak = 0;
                                t3 = "";
                                t4 = "";
                                rqsSecondThreeNo = "";
                                rqsCharacterNo = $("#pelakAzadFarsiNumber3").val();
                                rqsFirstTwoNo = $("input[id='pelakAzadFarsiNumber']").val();
                                rqsIRTwoNo = $("select[id='pelakTypeCombo'] option:selected").val();
                                var regexStr = "";
                                var len = $("input[id='pelakAzadFarsiNumber']").val().length;
                                var val = $("input[id='pelakAzadFarsiNumber']").val();

                                if (len !== 5) {
                                    $("#pazad").text("  پلاک وارد شده صحیح نمی باشد پلاک را به صورت کامل وارد نمایید");
                                }
                                else {
                                    var validm = /^[0-9]+$/;
                                    if (validm.test(val)) {
                                        $("#pazad").text("");
                                        selectpelak = 1;
                                        if ($("select[id='pelakTypeCombo'] option:selected").val() == "") {
                                            $("#pazad").text(" پلاک وارد شده صحیح نمی باشد شهر مورد نظر را انتخاب نمایید ");
                                        }
                                        else {
                                            $("#pazad").text("");
                                        }
                                    }
                                    else {
                                        $("#pazad").text(" پلاک وارد شده صحیح نمی باشد پلاک را به صورت کامل وارد نمایید");
                                        selectpelak = 0;
                                    }
                                }


                                truckTagType = true;
                                t2 = $("input[id='pelakAzadFarsiNumber']").val();
                                t1 = $("select[id='pelakTypeCombo'] option:selected").val();

                                break;
                            }
                        case "2":
                            {
                                truckTagType = false;
                                selectpelak = 0;
                                rqsIRTwoNo = $("input[id='pelakIrNum']").val();
                                rqsFirstTwoNo = $("input[name='pelakFirst']").val();
                                rqsCharacterNo = $("select[id='pelakCombo'] option:selected").val();
                                rqsSecondThreeNo = $("input[id='pelakCenter']").val();




                                var lenIR = $("input[id='pelakIrNum']").val().length;
                                var valIR = $("input[id='pelakIrNum']").val();

                                var lenCenter = $("input[id='pelakCenter']").val().length;
                                var valCenter = $("input[id='pelakCenter']").val();

                                var lenFirst = $("input[name='pelakFirst']").val().length;
                                var valFirst = $("input[name='pelakFirst']").val();



                                var selectadi = 0;

                                ////////////////////////////////////////////
                                if (lenIR !== 2) {
                                    selectadi = 1;
                                }
                                else {
                                    var validm = /^[0-9]+$/;
                                    if (validm.test(valIR)) {
                                        selectadi = 0;
                                        selectpelak = 1;
                                        if ($("select[id='pelakCombo'] option:selected").val() == "") {
                                            selectadi = 1;
                                        }
                                        else {
                                            selectadi = 0;
                                        }
                                        //////////////////////////////////////////////////////
                                        if (lenFirst !== 2) {
                                            selectadi = 1;
                                        }
                                        else {
                                            var validm = /^[0-9]+$/;
                                            if (validm.test(valFirst)) {
                                                selectadi = 0;
                                                selectpelak = 1;
                                                if ($("select[id='pelakCombo'] option:selected").val() == "") {
                                                    selectadi = 1;
                                                }
                                                else {
                                                    selectadi = 0;
                                                }
                                                //////////////////////////////////////////////
                                                if (lenCenter !== 3) {
                                                    selectadi = 1;
                                                }
                                                else {
                                                    var validm = /^[0-9]+$/;
                                                    if (validm.test(valCenter)) {
                                                        selectadi = 0;
                                                        selectpelak = 1;
                                                        if ($("select[id='pelakCombo'] option:selected").val() == "") {
                                                            selectadi = 1;
                                                        }
                                                        else {
                                                            selectadi = 0;
                                                        }
                                                    }
                                                    else {
                                                        selectadi = 1;
                                                        selectpelak = 0;
                                                    }
                                                }
                                            }
                                            else {
                                                selectadi = 1;
                                                selectpelak = 0;
                                            }
                                        }
                                    }
                                    else {
                                        selectadi = 1;
                                        selectpelak = 0;
                                    }
                                }
                                if (selectadi == 1) {
                                    selectpelak = 0;
                                    $("#pelakReq").text("پلاک وارد شده صحیح نمی باشد");
                                } else {
                                    selectpelak = 1;
                                    $("#pelakReq").text("");
                                }
                                /////////////////////////////////////////////////////////


                                if (rqsSecondThreeNo == "") {
                                    rqsCharacterNo = "";
                                    rqsFirstTwoNo = "";
                                }
                                truckTagType = false;
                                t1 = $("input[id='pelakIrNum']").val();
                                t2 = $("input[name='pelakFirst']").val();
                                t3 = $("select[id='pelakCombo'] option:selected").val();
                                t4 = $("input[id='pelakCenter']").val();
                                break;
                            }
                    }
                    $("#loading").show();

                    if (btnRegPelak == 1) {

                        if (selectpelak == 1) {
                            $.ajax({
                                url: "/Barname/Document/btnRegPelak",

                                data: {
                                    freeZoneCode: $("select[id='pelakTypeCombo'] option:selected").val(),
                                    freeZoneNo: $("#pelakAzadFarsiNumber").val(),
                                    freeZoneTwoDigit: $("#pelakAzadFarsiNumber3").val(),
                                    t1: $("input[id='pelakIrNum']").val(),
                                    t4: $("input[id='pelakCenter']").val(),
                                    t3: $("select[id='pelakCombo'] option:selected").val(),
                                    t2: $("input[name='pelakFirst']").val()
                                },
                                success: function (success) {
                                    //success = JSON.parse(success)
                                    $("#loading").hide();
                                    if (success.resultCode == 200) {
                                        toaster.toast("success", "پیغام سیستم", success.resultMessage);
                                        //      generalCls.GetDocumentById();
                                    }
                                    else {
                                        toaster.toast("error", "خطا", success.resultMessage);
                                    }
                                },
                                error: function (error) {

                                    $("#loading").hide();
                                    let raw = error.responseText || "";
                                    let jsonPart = null;


                                    let start = raw.indexOf("{");
                                    let end = raw.lastIndexOf("}");

                                    if (start !== -1 && end !== -1 && end > start) {
                                        let possibleJson = raw.substring(start, end + 1);

                                        try {
                                            jsonPart = JSON.parse(possibleJson);
                                        } catch (e) {
                                            console.log("JSON parse failed:", e);
                                        }
                                    }


                                    let msg = jsonPart?.resultMessage || jsonPart?.ResultMessage || "خطا در پردازش درخواست";


                                    toaster.toast("error", "خطا", msg);

                                    if (error.status == 401) {
                                        $("#loading").show()
                                        window.location = "/Barname/Account/Logout";
                                    }

                                }
                            });
                        } else {
                            $("#loading").hide();
                        }

                    }
                    else {

                    }
                }
                else {
                    return false;
                }
            },
            PlaqueSearchForbtnRegPelak: function () {

                $("#ThirdPartyInsurance").val('');
                $("#Activitylicense").val('');
                $("#CapacityFrom").val('');
                $("#CapacityTo").val('');
                $("#TypeofLoader").val('');
                if (true) {
                    var pelaktype = $("input[name='pelakIsAzad']:checked").val();
                    switch (pelaktype) {
                        case "1":
                            {

                                selectpelak = 0;
                                t3 = "";
                                t4 = "";
                                rqsSecondThreeNo = "";
                                rqsCharacterNo = $("#pelakAzadFarsiNumber3").val();
                                rqsFirstTwoNo = $("input[id='pelakAzadFarsiNumber']").val();
                                rqsIRTwoNo = $("select[id='pelakTypeCombo'] option:selected").val();
                                var regexStr = "";
                                var len = $("input[id='pelakAzadFarsiNumber']").val().length;
                                var val = $("input[id='pelakAzadFarsiNumber']").val();

                                if (len !== 5) {
                                    $("#pazad").text("  پلاک وارد شده صحیح نمی باشد پلاک را به صورت کامل وارد نمایید");
                                }
                                else {
                                    var validm = /^[0-9]+$/;
                                    if (validm.test(val)) {
                                        $("#pazad").text("");
                                        selectpelak = 1;
                                        if ($("select[id='pelakTypeCombo'] option:selected").val() == "") {
                                            $("#pazad").text(" پلاک وارد شده صحیح نمی باشد شهر مورد نظر را انتخاب نمایید ");
                                        }
                                        else {
                                            $("#pazad").text("");
                                        }
                                    }
                                    else {
                                        $("#pazad").text(" پلاک وارد شده صحیح نمی باشد پلاک را به صورت کامل وارد نمایید");
                                        selectpelak = 0;
                                    }
                                }


                                truckTagType = true;
                                t2 = $("input[id='pelakAzadFarsiNumber']").val();
                                t3 = $("input[id='pelakAzadFarsiNumber3']").val();
                                t1 = $("select[id='pelakTypeCombo'] option:selected").val();

                                break;
                            }
                        case "2":
                            {
                                truckTagType = false;
                                selectpelak = 0;
                                rqsIRTwoNo = $("input[id='pelakIrNum']").val();
                                rqsFirstTwoNo = $("input[name='pelakFirst']").val();
                                rqsCharacterNo = $("select[id='pelakCombo'] option:selected").val();
                                rqsSecondThreeNo = $("input[id='pelakCenter']").val();




                                var lenIR = $("input[id='pelakIrNum']").val().length;
                                var valIR = $("input[id='pelakIrNum']").val();

                                var lenCenter = $("input[id='pelakCenter']").val().length;
                                var valCenter = $("input[id='pelakCenter']").val();

                                var lenFirst = $("input[name='pelakFirst']").val().length;
                                var valFirst = $("input[name='pelakFirst']").val();



                                var selectadi = 0;

                                ////////////////////////////////////////////
                                if (lenIR !== 2) {
                                    selectadi = 1;
                                }
                                else {
                                    var validm = /^[0-9]+$/;
                                    if (validm.test(valIR)) {
                                        selectadi = 0;
                                        selectpelak = 1;
                                        if ($("select[id='pelakCombo'] option:selected").val() == "") {
                                            selectadi = 1;
                                        }
                                        else {
                                            selectadi = 0;
                                        }
                                        //////////////////////////////////////////////////////
                                        if (lenFirst !== 2) {
                                            selectadi = 1;
                                        }
                                        else {
                                            var validm = /^[0-9]+$/;
                                            if (validm.test(valFirst)) {
                                                selectadi = 0;
                                                selectpelak = 1;
                                                if ($("select[id='pelakCombo'] option:selected").val() == "") {
                                                    selectadi = 1;
                                                }
                                                else {
                                                    selectadi = 0;
                                                }
                                                //////////////////////////////////////////////
                                                if (lenCenter !== 3) {
                                                    selectadi = 1;
                                                }
                                                else {
                                                    var validm = /^[0-9]+$/;
                                                    if (validm.test(valCenter)) {
                                                        selectadi = 0;
                                                        selectpelak = 1;
                                                        if ($("select[id='pelakCombo'] option:selected").val() == "") {
                                                            selectadi = 1;
                                                        }
                                                        else {
                                                            selectadi = 0;
                                                        }
                                                    }
                                                    else {
                                                        selectadi = 1;
                                                        selectpelak = 0;
                                                    }
                                                }
                                            }
                                            else {
                                                selectadi = 1;
                                                selectpelak = 0;
                                            }
                                        }
                                    }
                                    else {
                                        selectadi = 1;
                                        selectpelak = 0;
                                    }
                                }
                                if (selectadi == 1) {
                                    selectpelak = 0;
                                    $("#pelakReq").text("پلاک وارد شده صحیح نمی باشد");
                                } else {
                                    selectpelak = 1;
                                    $("#pelakReq").text("");
                                }
                                /////////////////////////////////////////////////////////


                                if (rqsSecondThreeNo == "") {
                                    rqsCharacterNo = "";
                                    rqsFirstTwoNo = "";
                                }
                                truckTagType = false;
                                t1 = $("input[id='pelakIrNum']").val();
                                t2 = $("input[name='pelakFirst']").val();
                                t3 = $("select[id='pelakCombo'] option:selected").val();
                                t4 = $("input[id='pelakCenter']").val();
                                break;
                            }
                    }
                    $("#loading").show();

                    // FormShippingDocumentationSystemClick.getPelakType2();
                    // objformhelper.validate.init("frmpelaq")
                    //.success(function () {


                    if (selectpelak == 1) {
                        pelakv = 1;
                        $.ajax({
                            url: "/Barname/Document/PlaqueSearch",
                            data: {
                                t1: t1,
                                t2: t2,
                                t3: t3,
                                t4: t4,
                            },
                            success: function (result) {

                                result = JSON.parse(result)
                                $("#loading").hide();
                                if (result.resultCode == 200) {
                                    result = result.obj
                                    pelakv = 0;
                                    rqsIRTwoNo = 0;
                                    rqsFirstTwoNo = 0;
                                    rqsCharacterNo = 0;
                                    rqsSecondThreeNo = 0;
                                    $("#CapacityFrom").val(result.CapacityFrom);
                                    $("#CapacityTo").val(result.CapacityTo);

                                    CapacityTajmiTo = result.CapacityTo;

                                    fuelType = result.fuelType;

                                    $("#TypeofLoader").val(result.truckTypeName);
                                    havelicense = result.haveLicense;

                                    have3rd = result.have3rdInsurance;
                                    if (result.haveLicense == true) {
                                        $("#Activitylicense").val("دارد");
                                    }
                                    else {
                                        $("#Activitylicense").val("ندارد");
                                    }
                                    if (result.have3rdInsurance == true) {
                                        $("#ThirdPartyInsurance").val("دارد");
                                    }
                                    else {
                                        $("#ThirdPartyInsurance").val("ندارد");
                                    }
                                }
                                else {
                                    toaster.toast("error", "خطا", result.resultMessage)
                                }
                                btnRegPelak = 1;

                                FormShippingDocumentationSystemClick.btnRegPelakFunction();


                            },
                            error: function (error) {
                                $("#loading").hide();
                                toaster.toast("error", "خطا", error)
                                pelakv = 1;
                                $("#CapacityFrom").val('');
                                $("#CapacityTo").val('');
                                $("#TypeofLoader").val('');
                                $("#Activitylicense").val('');
                                $("#ThirdPartyInsurance").val('');


                                return false;
                            }
                        });
                    }

                    else {

                        $("#loading").hide();
                    }
                    //})
                    //     .error(function () {
                    //         
                    //         $("#loading").hide();
                    //    return false;
                    //});

                }
                else {
                    return false;
                }
                //})
                //.error(function () {
                //    return false;
                //});
                //  }, 3000)

            },
            DriverCarReturn: function () {
                if (true) {
                    generalCls.SetWizard(2);
                }
                else {
                    return false;
                }
            },
            DriverCarNext: function () {

                if (GlobalTajmiiFlag == true) {
                    if ($("div.mm-dropdown .option").val() != null) {
                        if ($("#DriverListTajmi").val() != null) {


                            t1 = null;
                            t2 = null;
                            t3 = null;
                            t4 = null;


                            //if ($('div.mm-dropdown > div.textfirst > div.plak > #pelakComboId ').val() != null) {
                            //    t1 = $('div.mm-dropdown > div.textfirst > div.plak > #pelakIrNum ').val();
                            //    t2 = $('div.mm-dropdown > div.textfirst > div.plak > #pelakFirst ').val();
                            //    t3 = $('div.mm-dropdown > div.textfirst > div.plak > #pelakComboId ').val();
                            //    t4 = $('div.mm-dropdown > div.textfirst > div.plak > #pelakCenter ').val();
                            //}
                            //else {
                            //    truckTagType = true;
                            //    t2 = $('div.mm-dropdown > div.textfirst  #pelakAzadFarsiNumber ').val();
                            //    t1 = $('div.mm-dropdown > div.textfirst  #FreeZoneId ').val();
                            //    t3 = $('div.mm-dropdown > div.textfirst  #pelakAzadLatinNumber3 ').val();
                            //    t4 = "";
                            //}

                            generalCls.SetWizard(4);

                            window.scroll(0, 0);
                        }
                        else {
                            toaster.toast("error", "خطا", "راننده انتخاب نشده است")
                        }
                    }
                    else {
                        toaster.toast("error", "خطا", "خودرو انتخاب نشده است")
                    }

                }
                else {
                    var irReq = $("#pelakIrNum").val();
                    var centerReq = $("#pelakCenter").val();
                    var comboReq = $("#pelakCombo").val();
                    var firstReq = $("[name='pelakFirst']").val();

                    //FormShippingDocumentationSystemClick.DriverSearch();
                    //FormShippingDocumentationSystemClick.PlaqueSearch();
                    setTimeout(function () {
                        var pelaktype = $("#frmpelaq input[name='pelakIsAzad']:checked").val();
                        var pelaktype = $("#frmpelaq input[name='pelakIsAzad']:checked").val();
                        switch (pelaktype) {
                            case "1":
                                {
                                    selectpelak = 0;
                                    t3 = "";
                                    t4 = "";
                                    rqsSecondThreeNo = "";
                                    rqsCharacterNo = "";
                                    rqsFirstTwoNo = $("input[id='pelakAzadFarsiNumber']").val();
                                    rqsIRTwoNo = $("select[id='pelakTypeCombo'] option:selected").val();
                                    var regexStr = "";
                                    var len = $("input[id='pelakAzadFarsiNumber']").val().length;
                                    var val = $("input[id='pelakAzadFarsiNumber']").val();

                                    if (len !== 5) {
                                        $("#pazad").text("پلاک وارد شده صحیح نمی باشد ");
                                    }
                                    else {
                                        var validm = /^[0-9]+$/;
                                        if (validm.test(val)) {
                                            $("#pazad").text("");
                                            selectpelak = 1;
                                            if ($("select[id='pelakTypeCombo'] option:selected").val() == "") {
                                                $("#pazad").text("پلاک وارد شده صحیح نمی باشد");
                                            }
                                            else {
                                                $("#pazad").text("");
                                            }
                                        }
                                        else {
                                            $("#pazad").text("پلاک وارد شده صحیح نمی باشد");
                                            selectpelak = 0;
                                        }
                                    }



                                    truckTagType = true;
                                    t2 = $("input[id='pelakAzadFarsiNumber']").val();
                                    t1 = $("select[id='pelakTypeCombo'] option:selected").val();
                                    t3 = $("#pelakAzadFarsiNumber3").val();
                                    break;
                                }
                            case "2":
                                {
                                    selectpelak = 0;
                                    rqsIRTwoNo = $("input[id='pelakIrNum']").val();
                                    rqsFirstTwoNo = $("input[name='pelakFirst']").val();
                                    rqsCharacterNo = $("select[id='pelakCombo'] option:selected").val();
                                    rqsSecondThreeNo = $("input[id='pelakCenter']").val();

                                    var lenIR = $("input[id='pelakIrNum']").val().length;
                                    var valIR = $("input[id='pelakIrNum']").val();

                                    var lenCenter = $("input[id='pelakCenter']").val().length;
                                    var valCenter = $("input[id='pelakCenter']").val();

                                    var lenFirst = $("input[name='pelakFirst']").val().length;
                                    var valFirst = $("input[name='pelakFirst']").val();

                                    var selectadi = 0;

                                    ////////////////////////////////////////////
                                    if (lenIR !== 2) {
                                        selectadi = 1;
                                    }
                                    else {
                                        var validm = /^[0-9]+$/;
                                        if (validm.test(valIR)) {
                                            selectadi = 0;
                                            selectpelak = 1;
                                            if ($("select[id='pelakCombo'] option:selected").val() == "") {
                                                selectadi = 1;
                                            }
                                            else {
                                                selectadi = 0;
                                            }
                                            //////////////////////////////////////////////////////
                                            if (lenFirst !== 2) {
                                                selectadi = 1;
                                            }
                                            else {
                                                var validm = /^[0-9]+$/;
                                                if (validm.test(valFirst)) {
                                                    selectadi = 0;
                                                    selectpelak = 1;
                                                    if ($("select[id='pelakCombo'] option:selected").val() == "") {
                                                        selectadi = 1;
                                                    }
                                                    else {
                                                        selectadi = 0;
                                                    }
                                                    //////////////////////////////////////////////
                                                    if (lenCenter !== 3) {
                                                        selectadi = 1;
                                                    }
                                                    else {
                                                        var validm = /^[0-9]+$/;
                                                        if (validm.test(valCenter)) {
                                                            selectadi = 0;
                                                            selectpelak = 1;
                                                            if ($("select[id='pelakCombo'] option:selected").val() == "") {
                                                                selectadi = 1;
                                                            }
                                                            else {
                                                                selectadi = 0;
                                                            }
                                                        }
                                                        else {
                                                            selectadi = 1;
                                                            selectpelak = 0;
                                                        }
                                                    }
                                                }
                                                else {
                                                    selectadi = 1;
                                                    selectpelak = 0;
                                                }
                                            }
                                        }
                                        else {
                                            selectadi = 1;
                                            selectpelak = 0;
                                        }
                                    }
                                    if (selectadi == 1) {
                                        selectpelak = 0;
                                        $("#pelakReq").text("پلاک وارد شده صحیح نمی باشد");
                                    } else {
                                        selectpelak = 1;
                                        $("#pelakReq").text("");
                                    }

                                    t1 = 0;
                                    t2 = 0;
                                    t3 = 0;
                                    t4 = 0;
                                    tag = 0;
                                    truckTagType = false;
                                    t1 = $("input[id='pelakIrNum']").val();
                                    t2 = $("input[name='pelakFirst']").val();
                                    t3 = $("select[id='pelakCombo'] option:selected").val();
                                    t4 = $("input[id='pelakCenter']").val();
                                    break;
                                }
                        }

                        if (true) {

                            if ((pelakv == 0)) {

                                //objformhelper.validate.init("frmpelaq")
                                //.success(function () {

                                if ((selectpelak == 1) && (DriverSearchv == 1)) {
                                    $("#loading").show();
                                    $("#loading").hide();
                                    t1forLoad = t1;
                                    t2forLoad = t2;
                                    t3forLoad = t3;
                                    t4forLoad = t4;

                                    btnaddLoadNumber = $("#gridfullLoad tr").length - 1;
                                    //      generalCls.GetDocumentById();
                                    generalCls.SetWizard(4);

                                    window.scroll(0, 0);

                                }

                            }
                            else if (pelakv == 1) {
                                toaster.toast("error", "خطا", error.statusText);

                            }
                        }
                        else {
                            return false;
                        }
                    }, 2000);

                }

            },

            //----------------------Kala--------------------
            showgrideKala: function () {
                $("#showgrideKala").val("");
                $("#frmBar").hide();
                $("#frmKalaFavorit").show();
                myDataTableKala.ajax.reload();
            },
            //افزودن کالا به لیست علاقه مندی ها
            btnRegPreKala: function () {

                if (true) {

                    objformhelper.validate.init("frmcommodityInsert")
                        .success(function () {

                            if (true) {
                                $("#loading").show();
                                $.ajax({
                                    url: "/Barname/Document/btnRegPreKala",
                                    data: {
                                        productId: $("#selecteditme").val(),
                                        txtKalaName: $("#txtLoadName").val(),
                                        txtKalaPackType: $("#ddBoxType").val(),
                                        txtKalaWeight: $("#txtWeight").val(),
                                        txtKalaBoxNum: $("#txtBoxNum").val()

                                    },
                                    success: function (success) {

                                        $("#loading").hide();
                                        //success = JSON.parse(success)
                                        if (success.resultCode == 200) {
                                            toaster.toast("success", "پیغام سیستم", success.resultMessage)
                                            myDataTableKala.ajax.reload();

                                        }
                                        else {

                                            toaster.toast("error", "خطا", success.resultMessage)
                                        }

                                    },
                                    error: function (error) {

                                        $("#loading").hide();
                                        let raw = error.responseText || "";
                                        let jsonPart = null;


                                        let start = raw.indexOf("{");
                                        let end = raw.lastIndexOf("}");

                                        if (start !== -1 && end !== -1 && end > start) {
                                            let possibleJson = raw.substring(start, end + 1);

                                            try {
                                                jsonPart = JSON.parse(possibleJson);
                                            } catch (e) {
                                                console.log("JSON parse failed:", e);
                                            }
                                        }


                                        let msg = jsonPart?.resultMessage || jsonPart?.ResultMessage || "خطا در پردازش درخواست";


                                        toaster.toast("error", "خطا", msg);

                                        if (error.status == 401) {
                                            $("#loading").show()
                                            window.location = "/Barname/Account/Logout";
                                        }

                                    }
                                });
                            }
                            else {
                                return false;
                            }
                        })
                        .error(function (e) {

                            return false;
                        });
                }
                else {
                    return false;
                }
            },
            btnDeleteDetailsKala: function () {

                var row = $(this).parents('tr');

                idKala = myDataTableKala.row(row).data()['id'];

                if (true) {
                    FormShippingDocumentationSystemClick.deleteKala();

                }
                else {
                    return false;
                }
            },
            deleteKala: function () {

                if (true) {
                    $("#loading").show();
                    $.ajax({
                        url: "/Barname/Document/btnDeletePreKala",
                        data: {
                            idKala: idKala,
                        },
                        success: function (success) {
                            //success = JSON.parse(success)
                            $("#loading").hide();
                            if (success.resultCode == 200) {
                                toaster.toast("success", "پیغام سیستم", success.resultMessage);
                                myDataTableKala.ajax.reload();
                            }
                            else {

                                toaster.toast("error", "خطا", success.resultMessage);
                            }
                        },
                        error: function (error) {

                            $("#loading").hide();
                            let raw = error.responseText || "";
                            let jsonPart = null;


                            let start = raw.indexOf("{");
                            let end = raw.lastIndexOf("}");

                            if (start !== -1 && end !== -1 && end > start) {
                                let possibleJson = raw.substring(start, end + 1);

                                try {
                                    jsonPart = JSON.parse(possibleJson);
                                } catch (e) {
                                    console.log("JSON parse failed:", e);
                                }
                            }


                            let msg = jsonPart?.resultMessage || jsonPart?.ResultMessage || "خطا در پردازش درخواست";


                            toaster.toast("error", "خطا", msg);

                            if (error.status == 401) {
                                $("#loading").show()
                                window.location = "/Barname/Account/Logout";
                            }

                        }
                    });
                }
                else {
                    return false;
                }
            },
            KalagridReturn: function () {
                if (true) {
                    $("#loading").hide();
                    $("#frmBar").show();
                    $("#modalFavoritKala").modal('hide');
                }
                else {
                    return false;
                }

            },



            //--- علاقه مندی ادرس
            btnRegPreSenderAddress: function () {

                if (true) {
                    objformhelper.init("frmmabda");
                    objformhelper.validate.init("frmmabda")
                        .success(function () {

                            if (true) {
                                $("#loading").show();
                                $.ajax({
                                    url: "/Barname/Document/PreAddressInsert",
                                    type: "post",
                                    data: {
                                        StateId: $("#ddStateSource").val(),
                                        CityId: $("#ddCitySource").val(),
                                        Address: $("#txtAddressSource").val(),
                                        PostalCode: $("#sourcePostalCode").val(),
                                        Source: true,
                                    },
                                    success: function (success) {
                                        $("#loading").hide();
                                       // success = JSON.parse(success)
                                        if (success.resultCode == 200) {
                                            myDataTableSenderAddress.ajax.reload();
                                            toaster.toast("success", "پیغام سیستم", success.resultMessage)


                                        }
                                        else {

                                            toaster.toast("error", "خطا", success.resultMessage)
                                        }

                                    },
                                    error: function (error) {

                                        $("#loading").hide();
                                        let raw = error.responseText || "";
                                        let jsonPart = null;


                                        let start = raw.indexOf("{");
                                        let end = raw.lastIndexOf("}");

                                        if (start !== -1 && end !== -1 && end > start) {
                                            let possibleJson = raw.substring(start, end + 1);

                                            try {
                                                jsonPart = JSON.parse(possibleJson);
                                            } catch (e) {
                                                console.log("JSON parse failed:", e);
                                            }
                                        }


                                        let msg = jsonPart?.resultMessage || jsonPart?.ResultMessage || "خطا در پردازش درخواست";


                                        toaster.toast("error", "خطا", msg);

                                        if (error.status == 401) {
                                            $("#loading").show()
                                            window.location = "/Barname/Account/Logout";
                                        }

                                    }
                                });
                            }
                            else {
                                return false;
                            }
                        })
                        .error(function (e) {

                            return false;
                        });
                }
                else {
                    return false;
                }
            },
            btnRegPreReceiverAddress: function () {

                if (true) {
                    objformhelper.init("formmagsad");
                    objformhelper.validate.init("formmagsad")
                        .success(function () {

                            if (true) {
                                $("#loading").show();
                                $.ajax({
                                    url: "/Barname/Document/PreAddressInsert",
                                    type: "post",
                                    data: {
                                        StateId: $("#ddStateDest").val(),
                                        CityId: $("#ddCityDest").val(),
                                        Address: $("#txtAddressDest").val(),
                                        PostalCode: $("#destPostalCode").val(),
                                        Source: false,
                                    },
                                    success: function (success) {
                                        $("#loading").hide();
                                        success = JSON.parse(success)
                                        if (success.resultCode == 200) {
                                            myDataTableReciverAddress.ajax.reload();
                                            toaster.toast("success", "پیغام سیستم", success.resultMessage)


                                        }
                                        else {

                                            toaster.toast("error", "خطا", success.resultMessage)
                                        }

                                    },
                                    error: function (error) {
                                        $("#loading").hide();
                                        toaster.toast("error", "خطا", error.statusText);

                                    }
                                });
                            }
                            else {
                                return false;
                            }
                        })
                        .error(function (e) {

                            return false;
                        });
                }
                else {
                    return false;
                }
            },
            //--مبدا
            selectSenderAddress: function () {
                if (true) {
                    $("#loading").show();

                    var row = $(this).parents('tr');

                    idDriver = myDataTableSenderAddress.row(row).data()['id'];



                    $("#ddStateSource").val(myDataTableSenderAddress.row(row).data()['stateId']).trigger("change");
                    ddCitySourceId = (myDataTableSenderAddress.row(row).data()['cityId']);
                    $("#sourcePostalCode").val(myDataTableSenderAddress.row(row).data()['postalCode']).trigger("change");
                    $("#txtAddressSource").val(myDataTableSenderAddress.row(row).data()['address']).trigger("change");

                    $("#frmSenderAddressrFavorit").hide();
                    $("#frmmabda").show();
                }
                else {
                    return false;
                }
            },
            DeleteSenderAddress: function () {

                if (true) {
                    let row = $(this).parents('tr');
                    let idrow = myDataTableSenderAddress.row(row).data()['id'];
                    $("#loading").show();
                    $.ajax({
                        url: "/Barname/Document/PreAddressDelete",
                        type: "Post",
                        data: {
                            id: idrow,
                        },
                        success: function (success) {
                            $("#loading").hide();
                            //success = JSON.parse(success)
                            if (success.resultCode == 200) {
                                toaster.toast("success", "پیغام سیستم", success.resultMessage)
                                myDataTableSenderAddress.ajax.reload();
                            }
                            else {



                                toaster.toast("error", "پیغام خطا", success.resultMessage)

                            }
                        },
                        error: function (error) {

                            $("#loading").hide();
                            let raw = error.responseText || "";
                            let jsonPart = null;


                            let start = raw.indexOf("{");
                            let end = raw.lastIndexOf("}");

                            if (start !== -1 && end !== -1 && end > start) {
                                let possibleJson = raw.substring(start, end + 1);

                                try {
                                    jsonPart = JSON.parse(possibleJson);
                                } catch (e) {
                                    console.log("JSON parse failed:", e);
                                }
                            }


                            let msg = jsonPart?.resultMessage || jsonPart?.ResultMessage || "خطا در پردازش درخواست";


                            toaster.toast("error", "خطا", msg);

                            if (error.status == 401) {
                                $("#loading").show()
                                window.location = "/Barname/Account/Logout";
                            }

                        }
                    });
                }
                else {
                    return false;
                }
            },
            //--مقصد
            selectReceiverAddress: function () {
                if (true) {
                    $("#loading").show();

                    var row = $(this).parents('tr');

                    let idrow = myDataTableReciverAddress.row(row).data()['id'];



                    $("#ddStateDest").val(myDataTableReciverAddress.row(row).data()['stateId']).trigger("change");
                    ddCityDestId = (myDataTableReciverAddress.row(row).data()['cityId']);
                    $("#destPostalCode").val(myDataTableReciverAddress.row(row).data()['postalCode']).trigger("change");
                    $("#txtAddressDest").val(myDataTableReciverAddress.row(row).data()['address']).trigger("change");

                    //$("#frmReciverAddressrFavorit").hide();
                    //$("#formmagsad").show();
                    $("#frmReceiverAddressrFavorit").hide();
                    $("#formmagsad").show();
                }
                else {
                    return false;
                }
            },
            DeleteReceiverAddress: function () {

                if (true) {
                    let row = $(this).parents('tr');
                    let idrow = myDataTableReciverAddress.row(row).data()['id'];
                    $("#loading").show();
                    $.ajax({
                        url: "/Barname/Document/PreAddressDelete",
                        type: "Post",
                        data: {
                            id: idrow,
                        },
                        success: function (success) {
                            $("#loading").hide();
                            success = JSON.parse(success)
                            if (success.resultCode == 200) {
                                toaster.toast("success", "پیغام سیستم", success.resultMessage)
                                myDataTableReciverAddress.ajax.reload();
                            }
                            else {



                                toaster.toast("error", "پیغام خطا", success.resultMessage)

                            }
                        },
                        error: function (error) {

                            $("#loading").hide();
                            toaster.toast("error", "خطا", error.statusText);

                        }
                    });
                }
                else {
                    return false;
                }
            },

            //-----------commodity---------------
            validationLoadChange: function () {
                if ($("#selecteditme").val() == "") {

                    $("#selecteditme").css({ "border-color": "#e7bebe", "background-color": "snow" });
                }
                else {
                    $("#spanvalidation").empty();
                    $("#selecteditme").css({ "border-color": "#b0dd9c", "background-color": "#f3f7f1" });
                    // FormShippingDocumentationSystemClick.btnAddLoadInsert();
                }


            },
            validationLoad: function () {

                $("#LoadNumberMinValidator").hide();

                FormShippingDocumentationSystemClick.btnAddLoadInsert();
                if ($("#selecteditme").val() == "") {

                    $("#selecteditme").css({ "border-color": "#e7bebe", "background-color": "snow" });

                }
                else {
                    $("#spanvalidation").empty();
                    $("#selecteditme").css({ "border-color": "#b0dd9c", "background-color": "#f3f7f1" });


                }


            },
            btnAddLoad: function () {

                $("#selecteditme").val('').trigger("change");
                $("#txtWeight").val('').trigger("change");
                $("#txtLoadName").val('').trigger("change");
                $("#txtLoadDetail").val('').trigger("change");
                $("#txtBoxNum").val('').trigger("change");
                $("#ddBoxType").val('').trigger("change");

                $("#frmcommodityInsert").data('formValidation').resetForm();

                $("#txtLoadNameValidationSpan").hide()
                $("#modaleditLoadInsert").modal('show');
            },



            btnkalafavorite: function () {

                $("#modalFavoritKala").modal('show');
            },

            btnAddLoadInsert: function () {

                if (true) {

                    if ($("#selecteditme").val() == "") {

                        $("#txtLoadNameValidationSpan").show()
                        return false
                    }
                    $("#txtLoadNameValidationSpan").hide()
                    btnaddLoadNumber = $("#gridfullLoad tr").length - 1;
                    if (btnaddLoadNumber <= 4) {
                        numberLoad = 1;

                        objformhelper.validate.init("frmcommodityInsert")
                            .success(function () {

                                $("#loading").show();
                                var productId = $("#selecteditme").val();
                                var weight = $("#txtWeight").val();
                                var txtLoadName = $("#txtLoadName").val();
                                var txtLoadDetail = $("#txtLoadDetail").val();
                                var boxNum = $("#txtBoxNum").val();
                                var packTypeId = $("#ddBoxType").val();
                                var ID = Math.floor((Math.random() * 10000) + 1).toString();
                                var loadItem = { ID: ID, ProductId: productId, Wheight: weight, PackTypeId: packTypeId, Description: txtLoadDetail, BoxNum: boxNum, Name: txtLoadName };
                                loadList.push(loadItem);

                                $("#selecteditme").val('').trigger("change");
                                $("#txtWeight").val('').trigger("change");
                                $("#txtLoadName").val('').trigger("change");
                                $("#txtLoadDetail").val('').trigger("change");
                                $("#txtBoxNum").val('').trigger("change");
                                $("#ddBoxType").val('').trigger("change");

                                $("#frmcommodityInsert").data('formValidation').resetForm();
                                $("#loading").hide();
                                $("#modaleditLoadInsert").modal('hide');
                                generalCls.fillgreadSelectedLoadfavorite();


                            })
                            .error(function () {
                                return false;
                            });
                    }
                    else {
                        toaster.toast("error", "خطا", "شما مجاز به درج 5 کالا می باشید");

                    }
                }
                else {
                    return false;
                }

            },
            //باتن انتخاب از علاقه مندی کالا
            btnAddSelectedKala: function () {

                if (true) {
                    $("#frmKalaFavorit").hide();
                    $("#frmBar").show();

                    btnaddLoadNumber = $("#gridfullLoad tr").length - 1;
                    if (btnaddLoadNumber <= 4) {
                        numberLoad = 1;
                        var row = $(this).parents('tr');

                        idKala = myDataTableKala.row(row).data()['id'];

                        $("#loading").show();
                        var productId = myDataTableKala.row(row).data()['productId'];
                        var weight = myDataTableKala.row(row).data()['weight'];
                        var txtLoadName = myDataTableKala.row(row).data()['name'];
                        var boxNum = myDataTableKala.row(row).data()['boxNum'];
                        var packTypeId = myDataTableKala.row(row).data()['packTypeId'];
                        var ID = Math.floor((Math.random() * 10000) + 1).toString();
                        var loadItem = { ID: ID, ProductId: productId, Wheight: weight, PackTypeId: packTypeId, BoxNum: boxNum, Name: txtLoadName };
                        loadList.push(loadItem);

                        $("#selecteditme").val('').trigger("change");
                        $("#txtWeight").val('').trigger("change");
                        $("#txtLoadName").val('').trigger("change");
                        $("#txtLoadDetail").val('').trigger("change");
                        $("#txtBoxNum").val('').trigger("change");
                        $("#ddBoxType").val('').trigger("change");

                        $("#frmcommodityInsert").data('formValidation').resetForm();
                        $("#loading").hide();
                        $("#modaleditLoadInsert").modal('hide');
                        generalCls.fillgreadSelectedLoadfavorite();



                    }
                    else {
                        toaster.toast("error", "خطا", "شما مجاز به درج 5 کالا می باشید");

                    }
                }
                else {
                    return false;
                }

            },
            GetCostSettings: function () {
                if (true) {
                    //$("#loading").show();
                    $.ajax({
                        url: "/Barname/Document/GetCostSettings",
                        /* url: "/Account/FormDocumentDetailsRegister.aspx",*/
                        function: "GetCostSettings",
                        data: { /*txtLoadsValue: $("#txtLoadsValue").val()*/ },
                        success: function (result) {

                            otpDuration = result.obj.otpValidityPeriod;
                            mapFlag = result.obj.mapFlag;

                            if (mapFlagShow == false) {
                                if (mapFlag) {
                                    $("#normalmabda").addClass("d-none");
                                    $("#normalmagsad").addClass("d-none");


                                    $("#MapPreviewBox").removeClass("d-none");
                                    $("#MapPreviewBoxmagsad").removeClass("d-none");
                              




                                }
                                else {

                                    $("#normalmabda").removeClass("d-none");
                                    $("#normalmagsad").removeClass("d-none");

                                    $("#MapPreviewBox").addClass("d-none");
                                    $("#MapPreviewBoxmagsad").addClass("d-none");


                                }
                                mapFlagShow = true;

                            }
                        },
                        error: function (error) {
                            $("#loading").hide();
                            toaster.toast("error", "خطا", error.statusText);

                        }
                    });
                }
                else {
                    return false;
                }
            },
            GetCostSettingsForTajmi: function () {

                if (true) {
                    //$("#loading").show();
                    $.ajax({
                        url: "/Barname/Document/GetCostSettings",
                        type: "get",
                        data: {},
                        success: function (res) {

                            /*  var info = generalJS.getUserInfo();*/
                            let result = res.obj;
                            GlobalTajmiiFlag = result.tajmiiFlag;



                            if (result.tajmiiFlag) {

                                FormShippingDocumentationSystemClick.GETUserFleetListTajmi();
                                //$("#frmpelaq").hide();
                                //$("#frmDriver").hide();
                                //$("#frmpelaqTajmi").show();
                                //$("#frmDriverTajmi").show();
                                $("#frmpelaq").addClass("d-none");
                                $("#frmDriver").addClass("d-none");
                                $("#frmpelaqTajmi").removeClass("d-none");
                                $("#frmDriverTajmi").removeClass("d-none");

                            }
                            else {
                                //$("#frmpelaq").show();
                                //$("#frmDriver").show();
                                //$("#frmpelaqTajmi").hide();
                                //$("#frmDriverTajmi").hide();
                                $("#frmpelaqTajmi").addClass("d-none");
                                $("#frmDriverTajmi").addClass("d-none");
                                $("#frmpelaq").removeClass("d-none");
                                $("#frmDriver").removeClass("d-none");
                            }

                            $("#loading").hide();


                        },
                        error: function (error) {
                            $("#loading").hide();
                            toaster.toast("error", "خطا", error.statusText);

                        }
                    });
                }
                else {
                    return false;
                }
            },
            GETUserFleetListTajmi: function () {

                if (true) {

                    $.ajax({
                        url: "/Barname/Document/GetCarAndDriverFulList",
                        data: {},
                        success: function (result) {

                            CarList = result.obj;

                            $("#PelakComboTajmi").empty();
                            $("#PelakComboTajmi").append(`<option value="" > انتخاب کنید </option>`);

                            if (result.resultCode == 200) {
                                result.obj.map(x => {
                                    if (x.hasFreeZoneCarTag == true) {
                                        $("#PelakComboTajmi").append(`<option value='${JSON.stringify(x).replace(/'/g, "&apos;")}'> ${x.freeZoneCarTag}-${x.freeZoneTwoDigit}- ${generalJS.getFreeZoneCityName(x.freeZoneId)}</option>`);
                                    }
                                    else {
                                        $("#PelakComboTajmi").append(`<option value='${JSON.stringify(x)}'> ${x.irTagPart1}-${generalJS.GetPelakChar(x.irTagPart3)}- ${x.irTagPart2}-${x.irTagPart4}</option>`);

                                    }
                                });

                                //let lat = parseFloat(result.obj[0].lat);
                                //let lon = parseFloat(result.obj[0].lon);

                                //if (lat && lon) {

                                //    RevereseMapLatSource(lat, lon);

                                //    RevereseMapLatDest(lat, lon);
                                //}

                            }


                        },
                        error: function (error) {
                            $("#loading").hide();
                            toaster.toast("error", "خطا", error.statusText);

                        }
                    });
                }
                else {
                    return false;
                }
            },
            changeComboPelaktajmi: function () {
                
                if (!!$("#PelakComboTajmi").val()) {


                    if (mapFlag) {
                        let selectedValue = $(this).val();
                        let selectedObj = JSON.parse(selectedValue);

                        let lat = parseFloat(selectedObj.lat);
                        let lon = parseFloat(selectedObj.lon);

                        if (lat && lon) {

                            RevereseMapLatSource(lat, lon);
                            LatSource = lat;
                            LngSource = lon;
                            setTimeout(x => {
                                showmapSource();
                                appMap.map.setView([lat, lon], 15);

                            }, 500)



                            RevereseMapLatDest(lat, lon);
                            //LatSource = lat;
                            //LngSource = lon;
                            //setTimeout(x => {
                            //    showmapSource();
                            //    appMap.map.setView([lat, lon], 15);

                            //}, 500)


                        }

                    }


                    $("#loading").show();
                    let pelakitem = JSON.parse($("#PelakComboTajmi").val());

                    let freighterId = pelakitem.ncarTag;
                    if (pelakitem.hasFreeZoneCarTag == true) {
                        rqsCharacterNo = $("#pelakAzadFarsiNumber3").val();
                        rqsFirstTwoNo = $("input[id='pelakAzadFarsiNumber']").val();
                        rqsIRTwoNo = $("#FreeZoneId2").val();
                        rqsSecondThreeNo = null;
                        GlobalfreighterId = pelakitem.ncarTag;
                        tajmiT3 = pelakitem.freeZoneCarTag;
                        tajmiT2 = pelakitem.freeZoneTwoDigit;
                        /*  tajmiT1 = generalJS.getFreeZoneCityName(pelakitem.freeZoneId);*/
                        tajmiT1 = generalJS.getFreeZoneCityName(pelakitem.freeZoneId);

                        rqsIRTwoNo = pelakitem.freeZoneId;
                        rqsCharacterNo = tajmiT2;
                        rqsFirstTwoNo = tajmiT3;


                    }
                    else if (pelakitem.hasFreeZoneCarTag == false) {
                        GlobalfreighterId = pelakitem.ncarTag
                        tajmiT1 = pelakitem.irTagPart1;
                        tajmiT2 = pelakitem.irTagPart2;
                        tajmiT3 = pelakitem.irTagPart3;
                        tajmiT4 = pelakitem.irTagPart4;

                        rqsIRTwoNo = tajmiT1;
                        rqsFirstTwoNo = tajmiT2;
                        rqsCharacterNo = tajmiT3;
                        rqsSecondThreeNo = tajmiT4;


                    }

                    //$.ajax({
                    //    url: "/Barname/Document/PlaqueSearch",

                    //    data: {
                    //        t1: rqsIRTwoNo,
                    //        t2: rqsFirstTwoNo,
                    //        t3: rqsCharacterNo,
                    //        t4: rqsSecondThreeNo,
                    //    },
                    //    success: function (res) {
                    //        let result = JSON.parse(res);



                    setTimeout(function () {

                        if (pelakitem != null) {
                            $("#ActivitylicenseTajmi").val("دارد");
                            $("#ThirdPartyInsuranceTajmi").val("دارد");

                            $("#TypeofLoaderTajmi").val(pelakitem.type)
                            $("#CapacityTajmi").val(pelakitem.capacityFrom);

                            $("#CapacityTajmiTo").val(pelakitem.capacityTo);

                            CapacityTajmiTo = pelakitem.capacityTo;
                            CapaUnit = pelakitem.capacityUnit;

                        }

                        /* var info = generalJS.getUserInfo();*/
                        var info = 10;

                        //if (info == 101) {
                        //    let CMODriverList = $("#DriverListTajmi");
                        //    CMODriverList.empty();
                        //    // CMODriverList.append("<option value=''>انتخاب کنید...</option>");
                        //    $.each(result, function () {
                        //        CMODriverList.append("<option value=" + info.NationalCode + ">" + info.FirstName + " " + info.LastName + "</option>");
                        //    });
                        //}

                        //else {
                        //------how to get selected pelak data -------
                        //$('div.mm-dropdown > div.textfirst > div.plak > #pelakIrNum ').val()
                        //--------------------------------------------



                        if (true) {

                            $.ajax({
                                url: "/Barname/Document/GetFleetDriverList",

                                data: { carTag: pelakitem.ncarTag },
                                success: function (result) {


                                    let CMODriverList = $("#DriverListTajmi");
                                    CMODriverList.empty();
                                    CMODriverList.append("<option value=''>انتخاب کنید...</option>");
                                    //$.each(result, function () {
                                    //    console.log("this select",this)
                                    //    CMODriverList.append("<option  data-attr3=" + this.mobile ?? "" + "  data-attr2=" + this.certificateNumber ?? "" + "    data-attr1=" + this.firstName + '_' + this.lastName.replace(/ /g, "_") + " value=" + this.nationalID ?? "" + ">" + this.firstName + " " + this.lastName ?? "" + " (" + this.nationalID ?? "" + ")" + "</option>");

                                    //});
                                    if (result.resultCode == 200) {
                                        result.obj.map(x => {
                                            CMODriverList.append(`<option data-attr3="${x.driverMobileNo ?? ''}"  data-attr2="${x.driverLicenceTrackingCode ?? ''}"    data-attr1="${x.driverName} ${x.driverLastName}" value='${JSON.stringify(x).replace(/'/g, "&apos;")}'> ${x.driverName ?? ""}  ${x.driverLastName ?? ""} (${x.driverNationalCode ?? ""})</option>`);

                                        })
                                    }
                                    $("#loading").hide();

                                },
                                error: function (error) {
                                    $("#loading").hide();
                                    toaster.toast("error", "خطا", error.statusText);

                                }
                            });
                        }
                        else {

                            return false;
                        }
                        /* }*/



                    }, 100);
                    //    },
                    //    error: function (error) {
                    //        $("#loading").hide();
                    //        toaster.toast("error", "خطا", error.statusText);
                    //        pelakv = 1;
                    //        $("#CapacityFrom").text('');
                    //        $("#CapacityTo").text('');
                    //        $("#TypeofLoader").text('');
                    //        $("#Activitylicense").text('');
                    //        $("#ThirdPartyInsurance").text('');


                    //        return false;
                    //    }
                    //});
                }















            },
            changeComboDriverClick: function () {


                if (true) {
                    if ($("#DriverListTajmi").val() != "") {
                        let Driveritem = JSON.parse($("#DriverListTajmi").val());
                        /* $("#loading").show();*/
                        //$.ajax({
                        //    url: "/Barname/Document/GetDrivers",

                        //    data: { nationalCode: $("#DriverListTajmi").val() },
                        //    success: function (result) {

                        if (Driveritem != null) {
                            if ($("#DriverListTajmi").val() != "") {

                                $("#txtDriverSearch").val($("#DriverListTajmi").val());

                                var selectedOption = $(this).find(":selected");
                                //var attributeNameValue = selectedOption.data("attr1");

                                //if (!!attributeNameValue) {

                                //    $("#DriverFullNameTajmi").val(attributeNameValue.replace(/_/g, " "));
                                //}
                                //else {

                                $("#DriverFullNameTajmi").val((Driveritem.driverName ?? " ") + "  " + (Driveritem.driverLastName ?? ""));
                                /* }*/

                                var attributeCertificateNumberValue = selectedOption.data("attr2");
                                if (!!attributeCertificateNumberValue) {

                                    $("#DriverNumberDriverLicenseTajmi").val(attributeCertificateNumberValue);
                                }
                                else {
                                    $("#DriverNumberDriverLicenseTajmi").val(Driveritem.certificateNo);

                                }



                                var attributeMobileValue = selectedOption.data("attr3");
                                if (attributeMobileValue != undefined) {

                                    $("#DriverMobileTajmi").val(attributeMobileValue);
                                }
                                else {
                                    $("#DriverMobileTajmi").val(`0${Driveritem.driverMobileNo}`);

                                }


                                $("#DriverEmploymentlicenseTajmi").val("دارد");
                                $("#DriverRatingTajmi").val(Driveritem.licenceStatus);
                            }
                            else {
                                $("#DriverEmploymentlicenseTajmi").val(" ");
                                $("#DriverMobileTajmi").val(" ");
                                $("#DriverNumberDriverLicenseTajmi").val(" ");
                                $("#DriverFullNameTajmi").val(" ");
                            }
                        }
                        else {
                            GlobalTajmiiFlag = false;



                            toaster.toast("error", "خطا", result.resultMessage)

                        }
                        $("#loading").hide();

                        //    },
                        //    error: function (error) {
                        //        $("#loading").hide();
                        //        DriverSearchv = 0;
                        //        toaster.toast("error", "خطا", error.statusText);
                        //        return false;
                        //    }
                        //});
                    }

                }
                else {
                    return false;
                }










            },
            BindCombo: function () {


                // Set
                var main = $('div.mm-dropdown .textfirst')
                var li = $('div.mm-dropdown > ul > li.input-option')
                var inputoption = $("div.mm-dropdown .option")
                var PelakTypeEnd = $("div.mm-dropdown .PelakTypeEnd")
                var default_text = 'پلاک  مورد نظر خود را انتخاب نمایید<img src="../img/Account/Wizard%203/ComboIcon.png" width="10" height="10" class="down" />';

                // Animation
                main.click(function () {
                    main.html(default_text);
                    li.toggle('fast');
                });

                // Insert Data
                li.click(function () {

                    // hide
                    li.toggle('fast');
                    var livalue = $(this).data('value');
                    var lihtml = $(this).html();
                    main.html(lihtml);
                    inputoption.val(livalue);
                    let x1 = $(this).attr('data-pflag');


                    PelakTypeEnd.val($(this).attr('data-pflag'));


                });

            },
            RefreshFleetListTajmi: function () {


                if (true) {

                    $.ajax({
                        url: "/Barname/Document/RefreshFleetList",


                        success: function (result) {


                            FormShippingDocumentationSystemClick.GETUserFleetListTajmi();
                        },
                        error: function (error) {
                            $("#loading").hide();
                            toaster.toast("error", "خطا", error.statusText);

                        }
                    });
                }
                else {
                    return false;
                }





            },

            GetInsuranceValue: function () {
                if (true) {

                    var listProductId = [];
                    for (var i = 0; i < loadList.length; i++) {
                        listProductId.push(loadList[i].ProductId);
                    }
                    $.ajax({
                        url: "/Account/FormDocumentDetailsRegister.aspx",
                        function: "GetInsuranceValue",
                        data: {
                            productIdList: JSON.stringify(listProductId),
                            coverLoadAndEmpty: $("#chkInsurance").val(),

                        },
                        success: function (result) {


                            //$("#txtbearingCost").text(generalCls.Comma(result.obj));
                            $("#txtbearingCost").val(0);

                            FormShippingDocumentationSystemClick.GetCostSettings();



                        },
                        error: function (error) {
                            $("#loading").hide();
                            toaster.toast("error", "خطا", error.statusText);

                        }
                    });
                }
                else {
                    return false;
                }

            },
            GetRemainCredit: function () {
                if (true) {
                    $("#loading").show();
                    $.ajax({
                        url: "/Account/FormDocumentDetailsRegister.aspx",
                        function: "RemainCredit",
                        data: { /*txtLoadsValue: $("#txtLoadsValue").val()*/ },
                        success: function (result) {
                            $("#loading").hide();
                            $("#txtRemainCredit").text(result);
                        },
                        error: function (error) {
                            $("#loading").hide();
                            toaster.toast("error", "خطا", error.statusText);
                        }
                    });
                }
                else {
                    return false;
                }
            },
            LoadShow: function () {
                $("#frmcommodity").hide();
                $("#frmLoadFavorit").show();
                myDataTableLoad.ajax.reload();
            },
            backToWizardKala: function () {
                $("#loading").hide();
                $("#frmLoadFavorit").hide();
                $("#frmcommodity").show();
            },
            selectLoad: function (ItemID) {
                if (true) {

                    $("#loading").show();
                    var SeletedItem = loadList.find(o => o.ID === ItemID);
                    $("#txtLoadName").val(SeletedItem.Name).trigger("change");
                    $("#selecteditme").val(SeletedItem.ProductId).trigger("change");
                    $("#ddBoxType").val(SeletedItem.PackTypeId).trigger("change");
                    $("#txtWeight").val(SeletedItem.Wheight).trigger("change");
                    $("#txtBoxNum").val(SeletedItem.BoxNum).trigger("change");
                    $("#txtLoadDetail").val(SeletedItem.Description).trigger("change");
                    $("#loading").hide();
                    $("#frmcommodity").show();
                    $("#frmLoadFavorit").hide();
                }
                else {
                    $("#loading").hide();
                    return false;
                }
            },
            btnDeleteLoad: function (ItemID) {
                if (true) {
                    $("#loading").show();
                    var objIndex = loadList.findIndex((obj => obj.ID == ItemID));

                    loadList.splice(objIndex, 1);
                    generalCls.fillgreadSelectedLoadfavorite();
                    $("#loading").hide();

                }
                else {
                    return false;
                }
            },
            UpdateLoadModal: function (ItemID) {
                if (true) {

                    $("#loading").show();
                    var SeletedItem = loadList.find(o => o.ID === ItemID);
                    idload = SeletedItem.ID;
                    txtLoadName = SeletedItem.Name;
                    selecteditme = SeletedItem.ProductId;
                    ddBoxType = SeletedItem.PackTypeId;
                    txtWeight = SeletedItem.Wheight;
                    txtBoxNum = SeletedItem.BoxNum;
                    txtLoadDetail = SeletedItem.Description;

                    $("#loading").hide();
                    //---------------------------------------------
                    $("#loadID").val(ItemID);
                    $("#txtLoadNameModal").val(txtLoadName).trigger("change");
                    $("#selecteditme2").val(selecteditme).trigger("change");
                    $("#ddBoxTypeModal").val(ddBoxType).trigger("change");
                    $("#txtWeightModal").val(txtWeight).trigger("change");;
                    $("#txtBoxNumModal").val(txtBoxNum).trigger("change");
                    $("#txtLoadDetailModal").val(txtLoadDetail).trigger("change");

                    $("#modaleditLoad").modal('show');
                }
                else {
                    $("#loading").hide();
                    return false;
                }
            },
            btnUpdateModal: function () {
                if (true) {
                    objformhelper.validate.init("frmcommodityModal")
                        .success(function () {
                            $("#loading").show();

                            var LoadName = $("#txtLoadNameModal").val();
                            var loadID = $("#loadID").val();
                            var packTypeId = $("#ddBoxTypeModal").val();
                            var weight = $("#txtWeightModal").val();
                            var boxNum = $("#txtBoxNumModal").val();
                            var txtLoadDetail = $("#txtLoadDetailModal").val();
                            var productId = $("#selecteditme").val();
                            var objIndex = loadList.findIndex((obj => obj.ID == loadID));

                            loadList[objIndex].Wheight = weight;
                            loadList[objIndex].PackTypeId = packTypeId;
                            loadList[objIndex].BoxNum = boxNum;
                            loadList[objIndex].Name = LoadName;
                            loadList[objIndex].Description = txtLoadDetail;
                            loadList[objIndex].ProductId = productId;

                            $("#selecteditme").val('').trigger("change");
                            $("#txtWeight").val('').trigger("change");
                            $("#txtLoadName").val('').trigger("change");
                            $("#txtLoadDetail").val('').trigger("change");
                            $("#txtBoxNum").val('').trigger("change");
                            $("#ddBoxType").val('').trigger("change");

                            $("#frmcommodityInsert").data('formValidation').resetForm();
                            generalCls.fillgreadSelectedLoadfavorite();
                            $("#modaleditLoad").modal('hide');


                        })
                        .error(function () {
                            return false;
                        });
                }
                else {
                    return false;
                }
            },
            commoditycheckbox: function () {
                if ($("#chkInsurance").is(':checked') == false) {
                    $("#chkInsurance").attr("isChecked", "false").trigger('change');
                    $("#chkInsurance").val("false").trigger('change');
                }
                else {
                    $("#chkInsurance").attr("isChecked", "true").trigger('change');
                    $("#chkInsurance").val("true").trigger('change');
                }
            },
            commodityRreturn: function () {
                if (true) {
                    havecertificateinload = driverHaveCertificate;
                    generalCls.SetWizard(3);
                }
                else {
                    return false;
                }
            },
            LoadCountfunc: function () {
                if (true) {

                    loadCount = loadList.length;
                }
                else {
                    return false;
                }
            },
            setcama: function () {

                var resultcoma = generalCls.Comma($("input[name='txtLoadsValue']").val());
                $("input[name='txtLoadsValue']").val(resultcoma);
            },
            commodityNextCount: function () {
                if ($("#txtLoadsValue").val() == "") {
                    value1 = 0;
                }
                else {
                    value1 = $("#txtLoadsValue").val();
                }
                FormShippingDocumentationSystemClick.LoadCountfunc();
                setTimeout(function () {
                    if (loadCount == 0) {
                        toaster.toast("error", "خطا", "افزودن کالا اجباری می باشد ")
                    }

                    else {
                        FormShippingDocumentationSystemClick.commodityNext();


                    }
                }, 2000);
            },
            commodityNext: function () {


                if (true) {

                    objformhelper.validate.init("frmcommodity")
                        .success(function () {

                            generalCls.SetWizard(5);
                            FormShippingDocumentationSystemClick.GetInsuranceValue();
                            /*  generalCls.ConfigurationMap();*/
                            window.scroll(0, $(document).height());
                            setTimeout(function () {
                                FormShippingDocumentationSystemClick.PreAddressFavoritOrigin();


                            }, 1500);



                        })
                        .error(function () {
                            return false;
                        });
                }
                else {
                    return false;
                }

            },

            PreAddressFavoritOrigin: function () {


                $("#loading").show();
                $.ajax({
                    url: "/Account/FormDocumentDetailsRegister.aspx",
                    function: "GetFavaoriteRoad",
                    data: { type: 1 },
                    success: function (result) {
                        ;
                        $("#loading").hide();
                        var crosshairIcon2 = {
                            iconUrl: '../Scripts/MainScript/MapFile/assets/images/icongreen.png',
                            iconSize: [37, 37], // size of the icon
                            iconAnchor: [37, 37], // point of the icon which will correspond to marker's location
                        };
                        if (result.resultCode == 200 && result.obj != null) {

                            appMap.addMarker({
                                name: 'advanced-marker',
                                latlng: {
                                    lat: result.obj.lat,
                                    lng: result.obj.lon
                                },
                                icon: crosshairIcon2,
                                popup: false
                            });

                            appMap.map.setView([result.obj.lat, result.obj.lon], 15);

                            if (result != null && result.obj != null && result.obj.lat != null) {
                                appMap.map.fire('click', {
                                    latlng: {
                                        lat: result.obj.lat,
                                        lng: result.obj.lon,
                                    },
                                });
                            }

                            LatSource = result.obj.lat;
                            LngSource = result.obj.lon;
                            $("#txtAddressSource").val(result.obj.address);
                            $("#ddStateSource").val(result.obj.stateMapName);
                            $("#ddCitySource").val(result.obj.cityMapName);
                            $("#Postal_code").val(result.obj.sourcePostalCode);
                        }


                    },
                    Complete: function () {
                    },
                    error: function (error) {
                        $("#loading").hide();
                        toaster.toast("error", "خطا", error.statusText);
                        return false;
                    }
                });

            },
            LoadingAndUnloadingOriginReturn: function () {
                if (true) {

                    generalCls.SetWizard(4);
                    /* generalCls.ConfigurationMap();*/
                }
                else {
                    return false;
                }
            },
            LoadingAndUnloadingOriginNext: function () {
                if (mapFlag == false) {
                    if (true) {
                        objformhelper.validate.init("frmmabdaMapFlage")
                            .success(function () {

                                $("#loading").show();
                                generalCls.SetWizard(6);
                                /*  generalCls.ConfigurationMap2();*/
                                FormShippingDocumentationSystemClick.PreAddressFavoritdestination();
                                $("#txtAddressSourceView").val($("#txtAddressOrgin2").val());
                                $("#SourcePostalCodeView").val($("#OrginPostalCode2").val());
                                $("SourceStateId").val($("#OrginState").val());
                                $("SourceCityId").val($("#OrginCity").val());

                                mapFlagSourcePostalCode = $("#OrginPostalCode2").val();
                                mapFlagSourceAddress = $("#txtAddressOrgin2").val();
                                mapFlagSourceCityTitle = $("#OrginCity :selected").text();
                                mapFlagSourceCityId = $("#OrginCity").val();
                                mapFlagSourceStateTitle = $("#OrginState :selected").text();
                                mapFlagSourceStateId = $("#OrginState").val();

                                $("#loading").hide();
                                window.scroll(0, $(document).height());

                            })
                            .error(function () {
                                return false;
                            });

                    }
                    else {
                        return false;
                    }
                }
                else {
                    if (true) {
                        objformhelper.validate.init("frmmabda")
                            .success(function () {
                                $("#loading").show();
                                generalCls.SetWizard(6);
                                /*  generalCls.ConfigurationMap2();*/
                                FormShippingDocumentationSystemClick.PreAddressFavoritdestination();
                                $("#txtAddressSourceView").val($("#txtAddressSource").val());
                                $("#SourcePostalCodeView").val($("#sourcePostalCode").val());
                                $("orginStateId").val($("#OrginState").val());
                                $("OrginCityId").val($("#OrginCity").val());
                                $("#loading").hide();
                                mapFlagSourceAddress = $("#txtAddressSource").val();
                                window.scroll(0, $(document).height());

                            })
                            .error(function () {
                                return false;
                            });

                    }
                    else {
                        return false;
                    }
                }

            },

            frmFavoritAddressReturnOrigin: function () {
                $("#frmmabda").show();
                $("#frmFavoritSource").hide();
            },

            PreAddressFavoritdestination: function () {



                $("#loading").show();
                $.ajax({
                    url: "/Account/FormDocumentDetailsRegister.aspx",
                    function: "GetFavaoriteRoad",
                    data: { type: 2 },
                    success: function (result) {

                        $("#loading").hide();

                        if (result.obj != null && result.resultCode == 200) {
                            appMap2.map.setView([result.obj.lat, result.obj.lon], 15);
                            if (result != null && result.obj != null && result.obj.lat != null) {
                                appMap2.map.fire('click', {
                                    latlng: {
                                        lat: result.obj.lat,
                                        lng: result.obj.lon,
                                    },
                                });
                            }
                            LatDestination = result.obj.lat;
                            LngDestination = result.obj.lon;
                            $("#txtAddressDest").val(result.obj.address_compact).trigger("change");
                            $("#txtAddressDestView").val(result.obj.address_compact).trigger("change");
                            $("#ddStateDest").val(result.obj.stateMapName).trigger("change");
                            $("#ddCityDest").val(result.obj.cityMapName).trigger("change");
                            $("#destPostalCode").val(result.obj.sourcePostalCode).trigger("change");
                            $("#destPostalCodeView").val(result.obj.sourcePostalCode).trigger("change")
                        }
                    },
                    Complete: function () {
                    },
                    error: function (error) {
                        $("#loading").hide();
                        toaster.toast("error", "خطا", error.statusText);
                        return false;
                    }
                });

            },

            LoadingAndUnloadingDestinationReturn: function () {
                if (true) {
                    generalCls.SetWizard(5);
                    window.scroll(0, $(document).height());
                }
                else {
                    return false;
                }
            },
            LoadingAndUnloadingDestinationNext: function () {
                if (true) {
                    objformhelper.validate.init("frmLoadingAndUnloadingDestination")
                        .success(function () {
                            $("#loading").show();
                            generalCls.SetWizard(7);
                            $("#loading").hide();


                        })
                        .error(function () {
                            return false;
                        });
                }
                else {
                    return false;
                }
            },
            LoadingRouteMapNext: function () {

                /*   if (mapFlag == false) {*/
                if (1 == 1) {

                    if (true) {
                        objformhelper.validate.init("formmagsadMapFlage")
                            .success(function () {
                                $("#loading").show();
                                generalCls.SetWizard(7);
                                /*    generalCls.ConfigurationMap3();*/
                                $("#txtAddressDestView").val($("#txtAddressDest").val());
                                $("#destPostalCodeView").val($("#destPostalCode").val());

                                $("#destPostalCodeView").val($("#destPostalCode2").val());





                                mapFlagDestinationPostalCode = $("#destPostalCode2").val();
                                mapFlagDestinationAddress = $("#txtAddressDest").val();
                                mapFlagDestinationCityTitle = $("#DestinationCity :selected").text();
                                mapFlagDestinationCityId = $("#DestinationCity").val();
                                mapFlagDestinationStateTitle = $("#DestinationState :selected").text();
                                mapFlagDestinationStateId = $("#DestinationState").val();

                                $("#loading").hide();
                                window.scroll(0, $(document).height());

                            })
                            .error(function () {
                                return false;
                            });
                    }
                    else {
                        return false;
                    }
                }
                else {
                    if (true) {
                        objformhelper.validate.init("formmagsad")
                            .success(function () {
                                $("#loading").show();
                                generalCls.SetWizard(7);
                                /*   generalCls.ConfigurationMap3();*/
                                $("#txtAddressDestView").val($("#txtAddressDest").val());
                                $("#destPostalCodeView").val($("#destPostalCode").val());
                                mapFlagDestinationAddress = $("#txtAddressDestView").val();
                                $("#loading").hide();
                                window.scroll(0, $(document).height());

                            })
                            .error(function () {
                                return false;
                            });
                    }
                    else {
                        return false;
                    }
                }

            },

            btnNextPriveiwInfo: function () {
                if (true) {
                    $("#loading").show();
                    generalCls.SetWizard(8);
                    $("#loading").hide();
                }
                else {
                    return false;
                }
            },

            btnBackDestination: function () {
                if (true) {
                    $("#loading").show();
                    generalCls.SetWizard(6);
                    window.scroll(0, $(document).height());
                    $("#loading").hide();
                }
                else {
                    return false;
                }
            },

            frmFavoritAddressReturnDest: function () {
                $("#formmagsad").show();
                $("#frmFavoritDest").hide();
            },
            //-------------------Fare
            //AddCredit: function () {
            //    if (true) {
            //        window.location = "Increasecredit.aspx";
            //    }
            //    else {
            //        return false;
            //    }
            //},
            resultKeraye: function () {
                var keraye = $("#txtkeraye").val();
                var pishkeraye = $("#txtPishKeraye").val();
                if (keraye == '') {
                    (pishkeraye = '0')
                    $("#txtPishKeraye").val('0');
                    (keraye = '0')
                    $("#txtkeraye").val('0');
                }

                if (pishkeraye == '') {
                    (pishkeraye = '0')
                    $("#txtPishKeraye").val('0');

                }
                var paskeraye = 0;
                var kerayeparseInt = parseInt(keraye.replace(/,/g, ''));
                var pishkerayeparseInt = parseInt(pishkeraye.replace(/,/g, ''));

                if ($("#txtPishKeraye").val() != "") {
                    if (pishkerayeparseInt <= kerayeparseInt) {

                        if (keraye.trim() != "" && pishkeraye.trim() != "") {

                            var keraye1 = $("#txtkeraye").val();
                            keraye = parseInt(keraye1.replace(/,/g, ''));
                            var pishkeraye1 = $("#txtPishKeraye").val();
                            pishkeraye = parseInt(pishkeraye1.replace(/,/g, ''));
                            $("#txtPasKeraye").val(keraye - pishkeraye);
                            $("#txtPasKeraye").val(generalCls.Comma($("#txtPasKeraye").val()));
                        }

                        else {

                            $("#txtPasKeraye").val('');
                        }
                    }
                    else {
                        toaster.toast("error", "خطا", "مبلغ پیش کرایه نمی تواند از کرایه بیشتر باشد")

                        $("#txtPishKeraye").val('');
                        $("#txtPasKeraye").val('');
                    }
                }
                else if (keraye.trim() == "" || pishkeraye.trim() == "") {
                    $("#txtPasKeraye").val('');
                }

            },
            btnTempRegister: function () {
                if ($("#sendsmsvalue").prop('checked') == true) {
                    SendSMS = true;
                }
                else {
                    SendSMS = false;
                }

                if (true) {
                    $("#loading").show();

                    //$.ajax({
                    //    url: "/Account/FormDocumentDetailsRegister.aspx",
                    //    function: "UpdateRegister",
                    //    data: {
                    //        IsDraft: IsDraft,


                    //        bearingCost: 0,

                    //        LicenseNumber: LicenseNumber,
                    //        destAddress: $("#txtAddressDest").val(),
                    //        //destCityId: $("#ddCityDest").val(),
                    //        destCityName: $("#ddCityDest option:selected").text(),
                    //        destPostalCode: $("#destPostalCode").val(),

                    //        driverNationalCode: $("#txtDriverSearch").val(),

                    //        postRent: $("#txtPasKeraye").val().replaceAll(',', ''),
                    //        preRent: $("#txtPishKeraye").val().replaceAll(',', ''),
                    //        receiverFullName: $("#txtReceiverFullName").val(),
                    //        receiverMobile: $("#txtReceiverMobile").val(),
                    //        receiverNationalCode: $("#txtReceiverNationalCode").val(),
                    //        receiverPostalCode: $("#txtReceiverPostalCode").val(),
                    //        receiverTelNumber: $("#txtReceiverTell").val(),
                    //        rent: $("#txtkeraye").val().replaceAll(',', ''),
                    //        senderFullName: $("#txtSenderFullName").val(),
                    //        senderMobile: $("#txtSenderMobile").val(),
                    //        senderNationalCode: $("#txtSenderNationalCode").val(),
                    //        senderPostalCode: $("#txtSenderPostalCode").val(),
                    //        senderTelNumber: $("#txtSenderTell").val(),
                    //        //sourceAddress: $("#txtAddressSource").val(),
                    //        //sourceCityId: $("#ddCitySource").val(),
                    //        //sourceCityName: $("#ddCitySource").val(),
                    //        //sourcePostalCode: $("#sourcePostalCode").val(),
                    //        //sourceStateId: $("#ddStateSource").val(),
                    //        //sourceStateName: $("#ddStateSource").val(),

                    //        sourceAddress: $("#txtAddressSource").val(),
                    //        sourceCityName: $("#ddCitySource option:selected").text(),
                    //        sourcePostalCode: $("#sourcePostalCode").val(),

                    //        t1: t1,
                    //        t2: t2,
                    //        t3: t3,
                    //        t4: t4,
                    //        value: $("#txtLoadsValue").val().replaceAll(',', ''),
                    //        SendSMS: $("#sendsmsvalue").is(':checked'),
                    //        loadList: JSON.stringify(loadList),
                    //        captcha: $("#DNTCaptchaText").val()
                    //    },
                    //    success: function (success) {

                    //        $("#loading").hide();
                    //        if (success.resultCode == 200) {
                    //            toaster.toast("success", "پیغام سیستم", "سند ذخیره شد")

                    //        }
                    //        else {
                    //            toaster.toast("error", "خطا", success.resultMessage);
                    //        }

                    //    },
                    //    error: function (error) {
                    //        $("#loading").hide();
                    //        toaster.toast("error", "خطا", error.statusText);
                    //        return false;
                    //    }
                    //});

                }
                else {
                    return false;
                }
            },
            btnRegister: function () {

                if ($("#sendsmsvalue").prop('checked') == true) {
                    SendSMS = true;
                }
                else {
                    SendSMS = false;
                }
                if (true) {
                    generalCls.showDetailsGetDocumentById();
                    //generalCls.SetWizard(9);

                }
                else {
                    return false;
                }
            },
            FareReturn: function () {
                if (true) {
                    generalCls.SetWizard(7);
                    /*   generalCls.ConfigurationMap2();*/
                }
                else {
                    return false;
                }
            },
            //--------------Details------------------
            btnRegisterFinishedReturn: function () {
                for (var i = 1; i <= $("#indexkalsa").val(); i++) {
                    $('#kala' + i + '').remove();

                }

                generalCls.SetWizard(7);

            },
            getLoadForDetails: function () {
                if (true) {
                    var i = 1;
                    for (i = 1; i <= loadList.length - 1; i++) {
                        $("#detailsKAla").append('<div id="kala' + i + '" class="col-md-12 mt-2 row">' + DetailsHtml + '</div>');


                    }

                    for (var j = 0; j <= loadList.length - 1; j++) {

                        $("#kala" + j + " [id='rqsLoadName']").text(loadList[j].Name + "   ");
                        $("#kala" + j + " [id='rqsWeight']").text(loadList[j].Wheight);
                        $("#indexkalsa").val(j);

                    }
                }
                else {
                    return false;
                }
            },
            showDetails: function () {

                FormShippingDocumentationSystemClick.getLoadForDetails();
                /*$("#pills-tab").addClass("d-none");*/
                //var ddCityDest = $("#ddCityDest").val();
                //var ddCitySource = $("#ddCitySource").val();
                var ddCityDest;
                var ddCitySource;


                if ($("#ddCitySource").val() != null && $("#ddCitySource").val() != "") {
                    var ddCitySource = $("#ddCitySource option:selected").text();
                } else if (citySourceMap != null) {
                    var ddCitySource = citySourceMap;
                }
                if ($("#ddCityDest").val() != null && $("#ddCityDest").val() != "") {
                    var ddCityDest = $("#ddCityDest option:selected").text();
                } else if (CityDestMap != null) {
                    var ddCityDest = CityDestMap;
                }

                if ((ddCityDest != ddCitySource) || (ddCityDest == null || ddCityDest == "") || (ddCitySource == null || ddCitySource == "")) {
                    $("#MSGBOXCity").show();
                }
                else {
                    $("#MSGBOXCity").hide();
                }

                //----------Sender-------------------

                if (!!senderFirstName) {
                    $("#rqsSender").val(senderFirstName + " " + senderLastName);
                } else {
                    $("#rqsSender").val(SenderOfficeName);
                }

                $("#rqsMobileSender").val(senderMobile);

                //نوع بارنامه فرستنده
                $("#txtSenderType").val($("#senderSelectType :selected").text());

                //----------Reciver-------------------

                if (!!receiverFirstName) {
                    $("#rqsReceiver").val(receiverFirstName + " " + receiverLastName);
                } else {
                    $("#rqsReceiver").val(receiverOfficeName);
                }

                $("#receiverFullNameFinal").text(receiverFirstName + " " + receiverLastName);
                $("#rqsMobileReceiver").val(receiverMobile);

                //نوع بارنامه گیرنده
                $("#txtReceiverType").val($("#receiverSelectType :selected").text());

                //----------Driver--------------------
                if (GlobalTajmiiFlag) {

                    driverFullName = $("#DriverFullNameTajmi").val();
                }
                $("#rqsDriver").val(driverFullName);

                var dateVal = $("#loadingDate").val();
                var timeVal = $("#loadingTime").val();

                var fulDateTime = dateVal + ' ' + '-' + ' ' + timeVal;

                $("#shippingStartDate").val(fulDateTime);


                var pelaktype = $("input[name='pelakIsAzad']:checked").val();
                switch (pelaktype) {
                    case "1":
                        {

                            selectpelak = 0;
                            t3 = "";
                            t4 = "";
                            rqsSecondThreeNo = "";
                            rqsCharacterNo = $("#pelakAzadFarsiNumber3").val();
                            rqsFirstTwoNo = $("input[id='pelakAzadFarsiNumber']").val();
                            rqsIRTwoNo = $("select[id='pelakTypeCombo'] option:selected").val();
                            var regexStr = "";
                            var len = $("input[id='pelakAzadFarsiNumber']").val().length;
                            var val = $("input[id='pelakAzadFarsiNumber']").val();

                            if (len !== 5) {
                                $("#pazad").text("  پلاک وارد شده صحیح نمی باشد پلاک را به صورت کامل وارد نمایید");
                            }
                            else {
                                var validm = /^[0-9]+$/;
                                if (validm.test(val)) {
                                    $("#pazad").text("");
                                    selectpelak = 1;
                                    if ($("select[id='pelakTypeCombo'] option:selected").val() == "") {
                                        $("#pazad").text(" پلاک وارد شده صحیح نمی باشد شهر مورد نظر را انتخاب نمایید ");
                                    }
                                    else {
                                        $("#pazad").text("");
                                    }
                                }
                                else {
                                    $("#pazad").text(" پلاک وارد شده صحیح نمی باشد پلاک را به صورت کامل وارد نمایید");
                                    selectpelak = 0;
                                }
                            }


                            truckTagType = true;
                            t2 = $("input[id='pelakAzadFarsiNumber']").val();
                            t3 = $("input[id='pelakAzadFarsiNumber3']").val();
                            t1 = $("select[id='pelakTypeCombo'] option:selected").val();

                            break;
                        }
                    case "2":
                        {
                            truckTagType = false;
                            selectpelak = 0;
                            rqsIRTwoNo = $("input[id='pelakIrNum']").val();
                            rqsFirstTwoNo = $("input[name='pelakFirst']").val();
                            rqsCharacterNo = $("select[id='pelakCombo'] option:selected").val();
                            rqsSecondThreeNo = $("input[id='pelakCenter']").val();




                            var lenIR = $("input[id='pelakIrNum']").val().length;
                            var valIR = $("input[id='pelakIrNum']").val();

                            var lenCenter = $("input[id='pelakCenter']").val().length;
                            var valCenter = $("input[id='pelakCenter']").val();

                            var lenFirst = $("input[name='pelakFirst']").val().length;
                            var valFirst = $("input[name='pelakFirst']").val();



                            var selectadi = 0;

                            ////////////////////////////////////////////
                            if (lenIR !== 2) {
                                selectadi = 1;
                            }
                            else {
                                var validm = /^[0-9]+$/;
                                if (validm.test(valIR)) {
                                    selectadi = 0;
                                    selectpelak = 1;
                                    if ($("select[id='pelakCombo'] option:selected").val() == "") {
                                        selectadi = 1;
                                    }
                                    else {
                                        selectadi = 0;
                                    }
                                    //////////////////////////////////////////////////////
                                    if (lenFirst !== 2) {
                                        selectadi = 1;
                                    }
                                    else {
                                        var validm = /^[0-9]+$/;
                                        if (validm.test(valFirst)) {
                                            selectadi = 0;
                                            selectpelak = 1;
                                            if ($("select[id='pelakCombo'] option:selected").val() == "") {
                                                selectadi = 1;
                                            }
                                            else {
                                                selectadi = 0;
                                            }
                                            //////////////////////////////////////////////
                                            if (lenCenter !== 3) {
                                                selectadi = 1;
                                            }
                                            else {
                                                var validm = /^[0-9]+$/;
                                                if (validm.test(valCenter)) {
                                                    selectadi = 0;
                                                    selectpelak = 1;
                                                    if ($("select[id='pelakCombo'] option:selected").val() == "") {
                                                        selectadi = 1;
                                                    }
                                                    else {
                                                        selectadi = 0;
                                                    }
                                                }
                                                else {
                                                    selectadi = 1;
                                                    selectpelak = 0;
                                                }
                                            }
                                        }
                                        else {
                                            selectadi = 1;
                                            selectpelak = 0;
                                        }
                                    }
                                }
                                else {
                                    selectadi = 1;
                                    selectpelak = 0;
                                }
                            }
                            if (selectadi == 1) {
                                selectpelak = 0;
                                $("#pelakReq").text("پلاک وارد شده صحیح نمی باشد");
                            } else {
                                selectpelak = 1;
                                $("#pelakReq").text("");
                            }
                            /////////////////////////////////////////////////////////


                            if (rqsSecondThreeNo == "") {
                                rqsCharacterNo = "";
                                rqsFirstTwoNo = "";
                            }
                            truckTagType = false;
                            t1 = $("input[id='pelakIrNum']").val();
                            t2 = $("input[name='pelakFirst']").val();
                            t3 = $("select[id='pelakCombo'] option:selected").val();
                            t4 = $("input[id='pelakCenter']").val();
                            break;
                        }
                }



                if ((t4 == null)) {
                    truckTagType = true;

                }
                if (GlobalTajmiiFlag) {

                    $("#rqsPelauq").val($("#PelakComboTajmi :selected").text());
                    $("#pelakFinal").text($("#PelakComboTajmi :selected").text());
                    $("#rqsCar").val($("#TypeofLoaderTajmi").val());
                }
                else {

                    $("#rqsCar").val(truckType);
                    if (t1 != '' && t2 != '') {
                        if (truckTagType == false) {
                            $("#rqsPelauq").val(" " + t1 + "|" + t4 + " " + $("select[id='pelakCombo'] option:selected").text() + " " + t2 + " ");
                            $("#pelakFinal").text(" " + t1 + "|" + t4 + " " + $("select[id='pelakCombo'] option:selected").text() + " " + t2 + " ");
                        }
                        else if (truckTagType == true) {
                            if (!t3) {
                                $("#rqsPelauq").val(" " + $("select[id='pelakTypeCombo'] option:selected").text() + "|" + t2 + " ");
                                $("#pelakFinal").text(" " + $("select[id='pelakTypeCombo'] option:selected").text() + "|" + t2 + " ");
                            }

                            else {
                                $("#rqsPelauq").val(" " + $("select[id='pelakTypeCombo'] option:selected").text() + "|" + t2 + " -" + t3 + " ");
                                $("#pelakFinal").text(" " + $("select[id='pelakTypeCombo'] option:selected").text() + "|" + t2 + " -" + t3 + " ");

                            }
                        }
                    }
                }



                //---------commodity------------------
                $("#rqsValue").val(generalCls.Comma($("#txtLoadsValue").val() + "    ریال "));
                if (insurance == true) {

                    $("#rqschkInsurance").val("دارد");
                }
                else {
                    $("#rqschkInsurance").val("ندارد");
                }
                //---------LoadingAndUnloadingOrigin
                if ($("#ddCitySource").val() != null && $("#ddCitySource").val() != "") {
                    $("#rqsOrigin").val($("#ddCitySource option:selected").text());
                    $("#OrginFinal").text($("#ddCitySource option:selected").text());
                } else if (citySourceMap != null) {
                    $("#rqsOrigin").val(citySourceMap);
                    $("#OrginFinal").text(citySourceMap);
                }


                if ($("#ddCityDest").val() != null && $("#ddCityDest").val() != "") {
                    $("#rqsDestination").val($("#ddCityDest option:selected").text());
                    $("#DestFinal").text($("#ddCityDest option:selected").text());
                } else if (CityDestMap != null) {
                    $("#rqsDestination").val(CityDestMap);
                    $("#DestFinal").text(CityDestMap);
                }


            },
            btnRegisterFinished: function () {
                $("#CapToken").on("click", function () {

                    $("#error-captxt").addClass("d-none");
                });
                $("#DNTCaptchaInputText").on("click", function () {

                    $("#error-captxtDNT").addClass("d-none");
                });
                $("#CaptchaCode").on("click", function () {

                    $("#error-CaptchaCode").addClass("d-none");
                });
                $("#error-captxt").addClass("d-none");
                $("#error-CaptchaCodet").addClass("d-none");
                let validform = "";
                if ($("#CapType").val() == 0) {

                    validform = $("#CapToken").val();
                }
                else if ($("#CapType").val() == 1) {
                    validform = $("#DNTCaptchaInputText").val();
                }
                else {
                    validform = $("#CaptchaCode").val();
                }
                if (!!validform) {


                    var pelaktype = $("input[name='pelakIsAzad']:checked").val();
                    switch (pelaktype) {
                        case "1":
                            {

                                selectpelak = 0;
                                t3 = "";
                                t4 = "";
                                rqsSecondThreeNo = "";
                                rqsCharacterNo = $("#pelakAzadFarsiNumber3").val();
                                rqsFirstTwoNo = $("input[id='pelakAzadFarsiNumber']").val();
                                rqsIRTwoNo = $("select[id='pelakTypeCombo'] option:selected").val();
                                var regexStr = "";
                                var len = $("input[id='pelakAzadFarsiNumber']").val().length;
                                var val = $("input[id='pelakAzadFarsiNumber']").val();

                                if (len !== 5) {
                                    $("#pazad").text("  پلاک وارد شده صحیح نمی باشد پلاک را به صورت کامل وارد نمایید");
                                }
                                else {
                                    var validm = /^[0-9]+$/;
                                    if (validm.test(val)) {
                                        $("#pazad").text("");
                                        selectpelak = 1;
                                        if ($("select[id='pelakTypeCombo'] option:selected").val() == "") {
                                            $("#pazad").text(" پلاک وارد شده صحیح نمی باشد شهر مورد نظر را انتخاب نمایید ");
                                        }
                                        else {
                                            $("#pazad").text("");
                                        }
                                    }
                                    else {
                                        $("#pazad").text(" پلاک وارد شده صحیح نمی باشد پلاک را به صورت کامل وارد نمایید");
                                        selectpelak = 0;
                                    }
                                }


                                truckTagType = true;
                                t2 = $("input[id='pelakAzadFarsiNumber']").val();
                                t1 = $("select[id='pelakTypeCombo'] option:selected").val();
                                t3 = $("input[id='pelakAzadFarsiNumber3']").val();

                                break;
                            }
                        case "2":
                            {

                                if (GlobalTajmiiFlag == false) {

                                    truckTagType = false;
                                    selectpelak = 0;
                                    rqsIRTwoNo = $("input[id='pelakIrNum']").val();
                                    rqsFirstTwoNo = $("input[name='pelakFirst']").val();
                                    rqsCharacterNo = $("select[id='pelakCombo'] option:selected").val();
                                    rqsSecondThreeNo = $("input[id='pelakCenter']").val();


                                    var lenIR = $("input[id='pelakIrNum']").val().length;
                                    var valIR = $("input[id='pelakIrNum']").val();

                                    var lenCenter = $("input[id='pelakCenter']").val().length;
                                    var valCenter = $("input[id='pelakCenter']").val();

                                    var lenFirst = $("input[name='pelakFirst']").val().length;
                                    var valFirst = $("input[name='pelakFirst']").val();

                                    var selectadi = 0;

                                    ////////////////////////////////////////////
                                    if (lenIR !== 2) {
                                        selectadi = 1;
                                    }
                                    else {
                                        var validm = /^[0-9]+$/;
                                        if (validm.test(valIR)) {
                                            selectadi = 0;
                                            selectpelak = 1;
                                            if ($("select[id='pelakCombo'] option:selected").val() == "") {
                                                selectadi = 1;
                                            }
                                            else {
                                                selectadi = 0;
                                            }
                                            //////////////////////////////////////////////////////
                                            if (lenFirst !== 2) {
                                                selectadi = 1;
                                            }
                                            else {
                                                var validm = /^[0-9]+$/;
                                                if (validm.test(valFirst)) {
                                                    selectadi = 0;
                                                    selectpelak = 1;
                                                    if ($("select[id='pelakCombo'] option:selected").val() == "") {
                                                        selectadi = 1;
                                                    }
                                                    else {
                                                        selectadi = 0;
                                                    }
                                                    //////////////////////////////////////////////
                                                    if (lenCenter !== 3) {
                                                        selectadi = 1;
                                                    }
                                                    else {
                                                        var validm = /^[0-9]+$/;
                                                        if (validm.test(valCenter)) {
                                                            selectadi = 0;
                                                            selectpelak = 1;
                                                            if ($("select[id='pelakCombo'] option:selected").val() == "") {
                                                                selectadi = 1;
                                                            }
                                                            else {
                                                                selectadi = 0;
                                                            }
                                                        }
                                                        else {
                                                            selectadi = 1;
                                                            selectpelak = 0;
                                                        }
                                                    }
                                                }
                                                else {
                                                    selectadi = 1;
                                                    selectpelak = 0;
                                                }
                                            }
                                        }
                                        else {
                                            selectadi = 1;
                                            selectpelak = 0;
                                        }
                                    }
                                    if (selectadi == 1) {
                                        selectpelak = 0;
                                        $("#pelakReq").text("پلاک وارد شده صحیح نمی باشد");
                                    } else {
                                        selectpelak = 1;
                                        $("#pelakReq").text("");
                                    }
                                    /////////////////////////////////////////////////////////


                                    if (rqsSecondThreeNo == "") {
                                        rqsCharacterNo = "";
                                        rqsFirstTwoNo = "";
                                    }

                                    truckTagType = false;
                                    t1 = $("input[id='pelakIrNum']").val();
                                    t2 = $("input[name='pelakFirst']").val();
                                    t3 = $("select[id='pelakCombo'] option:selected").val();
                                    t4 = $("input[id='pelakCenter']").val();

                                } else {

                                    //for tajmi
                                    let pelakitem = JSON.parse($("#PelakComboTajmi").val());



                                    if (pelakitem.hasFreeZoneCarTag == true) {
                                        rqsCharacterNo = $("#pelakAzadFarsiNumber3").val();
                                        rqsFirstTwoNo = $("input[id='pelakAzadFarsiNumber']").val();
                                        rqsIRTwoNo = $("#FreeZoneId2").val();
                                        rqsSecondThreeNo = null;

                                        t2 = pelakitem.freeZoneCarTag;
                                        t3 = pelakitem.freeZoneTwoDigit;
                                        t1 = pelakitem.freeZoneId;

                                    }
                                    else if (pelakitem.hasFreeZoneCarTag == false) {

                                        t1 = pelakitem.irTagPart1;
                                        t2 = pelakitem.irTagPart2;
                                        t3 = pelakitem.irTagPart3;
                                        t4 = pelakitem.irTagPart4;

                                    }

                                }


                                break;
                            }
                    }


                    if ($("#sendsmsvalue").prop('checked') == true) {
                        SendSMS = true;
                    }
                    else {
                        SendSMS = false;
                    }
                    var sourceCityNameF = "";
                    var DestCityNameF = "";
                    //if ($("#ddCitySource").val() != null && $("#ddCitySource").val() != "") {
                    //    sourceCityNameF = $("#ddCitySource option:selected").text();
                    //} else {
                    //    sourceCityNameF = citySourceMap;
                    //}

                    if (!mapFlag) {
                        sourceCityNameF = $("#ddCitySource option:selected").text();
                        DestCityNameF = $("#ddCityDest option:selected").text();
                    }
                    else {
                        sourceCityNameF = citySourceMap;
                        DestCityNameF = CityDestMap;
                    }

                    //if ($("#ddCityDest").val() != null && $("#ddCityDest").val() != "") {
                    //    DestCityNameF = $("#ddCityDest option:selected").text();

                    //} else {
                    //    DestCityNameF = CityDestMap;
                    //}


                    //فرستنده
                    var senderCompanyType = $("#txtSenderType").val();
                    var senderType = false;

                    if (senderCompanyType.includes('حقوقی')) {
                        senderType = true;
                        console.log("sender", senderType)
                    }
                    else {
                        senderType = false;
                    }
                    //گیرنده
                    var receiverCompanyType = $("#txtReceiverType").val();
                    var receicerType = false;

                    if (receiverCompanyType.includes('حقوقی')) {
                        receicerType = true;
                    }
                    else {
                        receicerType = false;
                    }

                    var dateVal = $("#loadingDate").val();
                    var timeVal = $("#loadingTime").val();

                    var fulDateTime = dateVal + ' ' + ' ' + timeVal;



                    //var miladiFull = new persianDate(fulDateTime).toDate();

                    $("#loading").show();

                    if ($("#CapType").val() == 0) {
                        $.ajax({
                            url: "/Barname/Document/UpdateRegisterNewNewOld",
                            type: "POST",
                            data: input = {
                                IsDraft: IsDraft,

                                DestinationAddress: $("#txtAddressDest").val(),

                                DestinationCityName: DestCityNameF,
                                destLatM: LatDestination,
                                destLonM: LngDestination,

                                /* DestinationCityName: $("#ddCityDest option:selected").text(),*/
                                DestinationPostalCode: $("#destPostalCode").val(),

                                driverNationalCode: JSON.parse($("#txtDriverSearch").val()).driverNationalCode,

                                postRent: $("#txtPasKeraye").val().replaceAll(',', ''),
                                preRent: $("#txtPishKeraye").val().replaceAll(',', ''),
                                receiverFirstName: $("#txtReceiverFirstName").val() ? $("#txtReceiverFirstName").val() : $("#txtReceiverOfficeName").val(),
                                receiverLastName: $("#txtReceiverLastName").val(),
                                receiverMobile: $("#txtReceiverMobile").val(),
                                receiverNationalCode: $("#txtReceiverNationalCode").val(),
                                receiverPostalCode: $("#txtReceiverPostalCode").val(),
                                receiverTelNumber: $("#txtReceiverTell").val(),
                                rent: $("#txtkeraye").val().replaceAll(',', ''),
                                senderFirstName: $("#txtSenderFirstName").val() ? $("#txtSenderFirstName").val() : $("#txtSenderOfficeName").val(),
                                senderLastName: $("#txtSenderLastName").val(),
                                senderMobile: $("#txtSenderMobile").val(),
                                senderNationalCode: $("#txtSenderNationalCode").val(),
                                senderPostalCode: $("#txtSenderPostalCode").val(),
                                senderTelNumber: $("#txtSenderTell").val(),

                                sourceAddress: $("#txtAddressSource").val(),

                                sourceLatM: LatSource,
                                sourceLonM: LngSource,
                                sourceCityName: sourceCityNameF,
                                sourcePostalCode: $("#SourcePostalCodeView").val(),

                                t1: t1,
                                t2: t2,
                                t3: t3,
                                t4: t4,
                                //freighterId: GlobalfreighterId,
                                value: $("#txtLoadsValue").val().replaceAll(',', ''),
                                SendSMS: $("#sendsmsvalue").is(':checked'),
                                loadList: JSON.stringify(loadList),
                                DNTCaptchaText: $("#DNTCaptchaText").val(),
                                DNTCaptchaInputText: $("#DNTCaptchaInputText").val(),
                                DNTCaptchaToken: $("#DNTCaptchaToken").val(),
                                capToken: $("#CapToken").val(),

                                //خود اظهاری تاریخ و ساعت شروع حمل
                                SelfDeclaredTimeOfStartShipment: fulDateTime,

                                //ثبت نوع بارنامه فرستنده و گیرنده
                                IsCompanySender: senderType,
                                IsCompanyReceiver: receicerType


                            },
                            success: function (res) {
                                
                                $("#loading").hide();


                                if (res.success == true) {


                                    toaster.toast("success", "پیغام سامانه", res.message);
                                    window.cap.reset();
                                }
                                else {
                                    if (res.message.includes("The HTTP status code of the response was not expected (401)")) {
                                        window.location = "/Barname/Account/Logout";
                                    } else {
                                        toaster.toast("error", "پیغام خطا", res.message);
                                        window.cap.reset();
                                    }
                                    return false;
                                }

                                let success = res.data;
                                if (success.resultCode == 200) {
                                    if (success.obj.isOtpNeeded == true) {
                                        objid = success.obj.id;
                                        toaster.toast("info", "لطفا کد احراز هویت ارسالی را وارد نمایید")
                                        $("#DocumentId").val(success.obj.id);
                                        $("#GetOptCodeModal").modal('show');
                                        downTime(false);
                                    } else {
                                        if (IsDraft) {
                                            toaster.toast("success", "موفق", "فایل پیش نویس با موفقیت افزوده شد");

                                            /* $("#dntCaptchaRefreshButton").click();*/
                                          /*  window.cap.reset();*/
                                        }
                                        else {
                                            objid = success.obj.id;
                                            FormShippingDocumentationSystemClick.showTrackingCode();
                                            $("#GoFinalStep").click();
                                            $("#pills-tab").addClass("d-none");
                                            /*$("#dntCaptchaRefreshButton").click();*/
                                           /* window.cap.reset();*/
                                        }
                                    }


                                }
                                else {
                                    /* $("#dntCaptchaRefreshButton").click()*/
                                    toaster.toast("error", "پیغام خطا", success.resultMessage);
                                    /* $("#dntCaptchaRefreshButton").click();*/
                                    window.cap.reset();
                                }

                            },
                            error: function (error) {
                                

                                /*$("#dntCaptchaRefreshButton").click()*/
                                $("#loading").hide();
                                toaster.toast("error", "پیغام خطا", error);
                                /* $("#dntCaptchaRefreshButton").click();*/
                                window.cap.reset();
                                return false;
                            }
                        });
                    }
                    else if ($("#CapType").val() == 1) {
                        $.ajax({
                            url: "/Barname/Document/UpdateRegisterNewOld",
                            type: "POST",
                            data: input = {
                                IsDraft: IsDraft,

                                DestinationAddress: $("#txtAddressDest").val(),

                                DestinationCityName: DestCityNameF,
                                destLatM: LatDestination,
                                destLonM: LngDestination,

                                /* DestinationCityName: $("#ddCityDest option:selected").text(),*/
                                DestinationPostalCode: $("#destPostalCode").val(),

                                driverNationalCode: JSON.parse($("#txtDriverSearch").val()).driverNationalCode,

                                postRent: $("#txtPasKeraye").val().replaceAll(',', ''),
                                preRent: $("#txtPishKeraye").val().replaceAll(',', ''),
                                receiverFirstName: $("#txtReceiverFirstName").val() ? $("#txtReceiverFirstName").val() : $("#txtReceiverOfficeName").val(),
                                receiverLastName: $("#txtReceiverLastName").val(),
                                receiverMobile: $("#txtReceiverMobile").val(),
                                receiverNationalCode: $("#txtReceiverNationalCode").val(),
                                receiverPostalCode: $("#txtReceiverPostalCode").val(),
                                receiverTelNumber: $("#txtReceiverTell").val(),
                                rent: $("#txtkeraye").val().replaceAll(',', ''),
                                senderFirstName: $("#txtSenderFirstName").val() ? $("#txtSenderFirstName").val() : $("#txtSenderOfficeName").val(),
                                senderLastName: $("#txtSenderLastName").val(),
                                senderMobile: $("#txtSenderMobile").val(),
                                senderNationalCode: $("#txtSenderNationalCode").val(),
                                senderPostalCode: $("#txtSenderPostalCode").val(),
                                senderTelNumber: $("#txtSenderTell").val(),
                                //sourceAddress: $("#txtAddressSource").val(),
                                //sourceCityId: $("#ddCitySource").val(),
                                //sourceCityName: $("#ddCitySource").val(),
                                //sourcePostalCode: $("#sourcePostalCode").val(),
                                //sourceStateId: $("#ddStateSource").val(),
                                //sourceStateName: $("#ddStateSource").val(),

                                sourceAddress: $("#txtAddressSource").val(),
                                //sourceCityName: $("#ddCitySource option:selected").text(),
                                //sourcePostalCode: $("#sourcePostalCode").val(),

                                sourceLatM: LatSource,
                                sourceLonM: LngSource,
                                sourceCityName: sourceCityNameF,
                                sourcePostalCode: $("#SourcePostalCodeView").val(),

                                t1: t1,
                                t2: t2,
                                t3: t3,
                                t4: t4,
                                //freighterId: GlobalfreighterId,
                                value: $("#txtLoadsValue").val().replaceAll(',', ''),
                                SendSMS: $("#sendsmsvalue").is(':checked'),
                                loadList: JSON.stringify(loadList),
                                DNTCaptchaText: $("#DNTCaptchaText").val(),
                                DNTCaptchaInputText: $("#DNTCaptchaInputText").val(),
                                DNTCaptchaToken: $("#DNTCaptchaToken").val(),
                                capToken: null,

                                //خود اظهاری تاریخ و ساعت شروع حمل
                                SelfDeclaredTimeOfStartShipment: fulDateTime,

                                //ثبت نوع بارنامه فرستنده و گیرنده
                                IsCompanySender: senderType,
                                IsCompanyReceiver: receicerType


                            },

                            //data: input = {
                            //    "IsDraft": false,
                            //    "DestinationAddress": "زنجان، محله اعتمادیه، جمهوری اسلامی، خیابان ۸ - احمد تختی",
                            //    "DestinationCityName": "زنجان",
                            //    "destLatM": 36.67045670874926,
                            //    "destLonM": 48.5002613067627,
                            //    "DestinationPostalCode": "4444444444",
                            //    "driverNationalCode": "0780795083",
                            //    "postRent": 20000000,
                            //    "preRent": 0,
                            //    "receiverFullName": "رضا ولی پناه",
                            //    "receiverMobile": "09186666685",
                            //    "receiverNationalCode": "",
                            //    "receiverPostalCode": "",
                            //    "receiverTelNumber": "",
                            //    "rent": 20000000,
                            //    "senderFullName": "پیمان وفادوس سبزواری",
                            //    "senderMobile": "09157146501",
                            //    "senderNationalCode": "",
                            //    "senderPostalCode": "",
                            //    "senderTelNumber": "",
                            //    "sourceAddress": "تهران، محله دانشگاه تهران، فلسطین، بزرگمهر",
                            //    "sourceLatM": 35.704035578275594,
                            //    "sourceLonM": 51.404342651367195,
                            //    "sourceCityName": "تهران",
                            //    "sourcePostalCode": "1111111111",
                            //    "t1": 55,
                            //    "t2": 55,
                            //    "t3": 2,
                            //    "t4": 555,
                            //    "freighterId": "6160272",
                            //    "value": "2000000000",
                            //    "SendSMS": "false",
                            //    "loadList": JSON.stringify([{ "ID": "47", "ProductId": "987", "Wheight": "1", "PackTypeId": "10", "Description": "", "BoxNum": "10", "Name": "سس" }]),
                            //    DNTCaptchaText: $("#DNTCaptchaText").val(),
                            //    DNTCaptchaInputText: $("#DNTCaptchaInputText").val(),
                            //    DNTCaptchaToken: $("#DNTCaptchaToken").val()

                            //},
                            success: function (res) {
                                //$("#dntCaptchaRefreshButton").click()
                                //$("#loading").hide();

                                //if (res.success == true) {


                                //    toaster.toast("success", "پیغام سامانه", res.message);
                                //}
                                //else {

                                //    toaster.toast("error", "پیغام خطا", res.message);
                                //    return false;
                                //}



                                //let success = res.data;
                                ///* success = JSON.parse(success)*/
                                //if (success.resultCode == 200) {
                                //    if (IsDraft) {
                                //        toaster.toast("success", "موفق", "فایل پیش نویس با موفقیت افزوده شد")
                                //    }
                                //    else {
                                //        objid = success.obj;

                                //        FormShippingDocumentationSystemClick.showTrackingCode();
                                //        $("#GoFinalStep").click()
                                //    }

                                //}
                                //else {
                                //    console.log("success: ", res.message)
                                //    toaster.toast("error", "خطا", success.resultMessage)
                                //}
                                /*  $("#dntCaptchaRefreshButton").click()*/
                                $("#loading").hide();

                                
                                if (res.success == true) {


                                    toaster.toast("success", "پیغام سامانه", res.message);
                                    $("#dntCaptchaRefreshButton").click();
                                }
                                else {
                                    if (res.message.includes("The HTTP status code of the response was not expected (401)")) {
                                        window.location = "/Barname/Account/Logout";
                                    } else {
                                        toaster.toast("error", "پیغام خطا", res.message);
                                        $("#dntCaptchaRefreshButton").click();
                                    }
                                    return false;
                                }

                                let success = res.data;
                                if (success.resultCode == 200) {
                                    if (success.obj.isOtpNeeded == true) {
                                        objid = success.obj.id;
                                        toaster.toast("info", "لطفا کد احراز هویت ارسالی را وارد نمایید")
                                        $("#DocumentId").val(success.obj.id);
                                        $("#GetOptCodeModal").modal('show');
                                        downTime(false);
                                    } else {
                                        if (IsDraft) {
                                            toaster.toast("success", "موفق", "فایل پیش نویس با موفقیت افزوده شد");

                                         /*   $("#dntCaptchaRefreshButton").click();*/
                                            /*  window.cap.reset();*/
                                        }
                                        else {
                                            objid = success.obj.id;
                                            FormShippingDocumentationSystemClick.showTrackingCode();
                                            $("#GoFinalStep").click();
                                            $("#pills-tab").addClass("d-none");
                                        /*    $("#dntCaptchaRefreshButton").click();*/
                                            /* window.cap.reset();*/
                                        }
                                    }


                                }
                                else {

                                    toaster.toast("error", "پیغام خطا", success.resultMessage);
                                    $("#dntCaptchaRefreshButton").click();
                                    /* window.cap.reset();*/
                                }

                            },
                            error: function (error) {
                                
                                $("#loading").hide();
                                toaster.toast("error", "پیغام خطا", error);
                                $("#dntCaptchaRefreshButton").click();
                                /*   window.cap.reset();*/
                                return false;
                            }
                        });
                    }
                    else {
                        $.ajax({
                            url: "/Barname/Document/UpdateRegisterNewNew",
                            type: "POST",
                            data: {
                                IsDraft: IsDraft,
                                DestinationAddress: $("#txtAddressDest").val(),

                                DestinationCityName: DestCityNameF,
                                destLatM: LatDestination,
                                destLonM: LngDestination,
                                DestinationPostalCode: $("#destPostalCode").val(),

                                driverNationalCode: JSON.parse($("#txtDriverSearch").val()).driverNationalCode,

                                postRent: $("#txtPasKeraye").val().replaceAll(',', ''),
                                preRent: $("#txtPishKeraye").val().replaceAll(',', ''),
                                receiverFirstName: $("#txtReceiverFirstName").val() ? $("#txtReceiverFirstName").val() : $("#txtReceiverOfficeName").val(),
                                receiverLastName: $("#txtReceiverLastName").val(),
                                receiverMobile: $("#txtReceiverMobile").val(),
                                receiverNationalCode: $("#txtReceiverNationalCode").val(),
                                receiverPostalCode: $("#txtReceiverPostalCode").val(),
                                receiverTelNumber: $("#txtReceiverTell").val(),
                                rent: $("#txtkeraye").val().replaceAll(',', ''),
                                senderFirstName: $("#txtSenderFirstName").val() ? $("#txtSenderFirstName").val() : $("#txtSenderOfficeName").val(),
                                senderLastName: $("#txtSenderLastName").val(),
                                senderMobile: $("#txtSenderMobile").val(),
                                senderNationalCode: $("#txtSenderNationalCode").val(),
                                senderPostalCode: $("#txtSenderPostalCode").val(),
                                senderTelNumber: $("#txtSenderTell").val(),
                                //sourceAddress: $("#txtAddressSource").val(),
                                //sourceCityId: $("#ddCitySource").val(),
                                //sourceCityName: $("#ddCitySource").val(),
                                //sourcePostalCode: $("#sourcePostalCode").val(),
                                //sourceStateId: $("#ddStateSource").val(),
                                //sourceStateName: $("#ddStateSource").val(),

                                sourceAddress: $("#txtAddressSource").val(),
                                sourceLatM: LatSource,
                                sourceLonM: LngSource,
                                sourceCityName: sourceCityNameF,
                                sourcePostalCode: $("#SourcePostalCodeView").val(),

                                t1: t1,
                                t2: t2,
                                t3: t3,
                                t4: t4,
                                freighterId: GlobalfreighterId,
                                value: $("#txtLoadsValue").val().replaceAll(',', ''),
                                SendSMS: $("#sendsmsvalue").is(':checked'),
                                loadList: JSON.stringify(loadList),
                                DNTCaptchaText: null,
                                DNTCaptchaInputText: null,
                                DNTCaptchaToken: null,
                                capToken: null,
                                captchaCode: $("#CaptchaCode").val(),
                                captchaToken: $("#captchaToken").val(),
                                //خود اظهاری تاریخ و ساعت شروع حمل
                                SelfDeclaredTimeOfStartShipment: fulDateTime
                            },
                            success: function (res) {

                                $("#loading").hide();

                                
                                if (res.success == true) {


                                    toaster.toast("success", "پیغام سامانه", res.message);
                                    $("#btnReloadCaptcha").click();
                                }
                                else {
                                    if (res.message.includes("The HTTP status code of the response was not expected (401)")) {
                                        window.location = "/Barname/Account/Logout";
                                    } else {

                                    toaster.toast("error", "پیغام خطا", res.message);
                                    $("#btnReloadCaptcha").click();
                                    }
                                    return false;
                                }

                                let success = res.data;
                                if (success.resultCode == 200) {
                                    if (success.obj.isOtpNeeded == true) {
                                        objid = success.obj.id;
                                        toaster.toast("info", "لطفا کد احراز هویت ارسالی را وارد نمایید")
                                        $("#DocumentId").val(success.obj.id);
                                        $("#GetOptCodeModal").modal('show');
                                        downTime(false);
                                    } else {
                                        if (IsDraft) {
                                            toaster.toast("success", "موفق", "فایل پیش نویس با موفقیت افزوده شد");
                                        /*    $("#btnReloadCaptcha").click();*/
                                            /* window.cap.reset();*/
                                        }
                                        else {
                                            objid = success.obj.id;
                                            FormShippingDocumentationSystemClick.showTrackingCode();
                                            $("#GoFinalStep").click();
                                            $("#pills-tab").addClass("d-none");
                                           /* $("#btnReloadCaptcha").click();*/
                                            /* window.cap.reset();*/
                                        }
                                    }


                                }
                                else {

                                    toaster.toast("error", "خطا", success.resultMessage);
                                    $("#btnReloadCaptcha").click();
                                    /*  window.cap.reset();*/
                                }

                            },
                            error: function (error) {
                                
                                $("#loading").hide();
                                toaster.toast("error", "خطا", error);
                                $("#btnReloadCaptcha").click();
                                /*  window.cap.reset();*/
                                return false;
                            }
                        });
                    }

                }
                else {
                    if ($("#CapType").val() == 0) {
                        $("#error-captxt").removeClass("d-none");
                    }
                    else if ($("#CapType").val() == 1) {
                        $("#error-captxtDNT").removeClass("d-none");
                    }
                    else {
                        $("#error-CaptchaCode").removeClass("d-none");

                    }

                    return false;
                }
            },
            showTrackingCode: function () {
                $("#loading").show();
                if (true) {
                    $.ajax({
                        url: "/Barname/Document/showTrackingCode",
                        function: "showTrackingCode",
                        data: {
                            id: objid
                        },
                        success: function (result) {

                            $("#loading").hide();
                            $("#TrackingCodeNumber").val(result);
                            /* $("#TrackingCodeNumber").text(result);*/
                        },
                        error: function (error) {
                            $("#loading").hide();
                            toaster.toast("error", "خطا", "مشکلی در دریافت کد رهگیری پیش آمده است")
                            return false;
                        }
                    });

                }
                else {
                    return false;
                }
            },
            NewRegister: function () {
                window.location = "/Barname/Document/HagigiHogugi";
                $("#pills-tab").removeClass("d-none");
            },
            printbarbarg: function () {
                if (true) {
                    $("#modalPrint").modal('show');
                }
                else {
                    return false;
                }
                //window.print();
            },

            PrintSender: function () {
                if (true) {
                    window.open('../Print/PrintSender.aspx', '_blank');
                }
                else {
                    return false;
                }
            },
            PrintReceiver: function () {
                if (true) {
                    window.open('../Print/PrintReceiver.aspx', '_blank');
                }
                else {
                    return false;
                }
            },
            PrintDriver: function () {
                if (true) {
                    window.open('../Print/PrintDriver.aspx', '_blank');
                }
                else {
                    return false;
                }
            },
            sendsmsvalue: function () {


                if ($("#sendsmsvalue").prop('checked') == true) {
                    SendSMS = true;
                    SMSvalue = $(this).val();
                    //$("#txtnotifyCost").text(generalCls.Comma(0));
                    $("#txtnotifyCost").val(0);
                    notifyCosttxt = 0;
                    $("#loading").hide();
                    FormShippingDocumentationSystemClick.GetCostSettings();
                }
                else {
                    SendSMS = false;
                    //$("#txtnotifyCost").text("0");
                    $("#txtnotifyCost").val(0);
                    notifyCosttxt = 0;
                    FormShippingDocumentationSystemClick.GetCostSettings();
                }

            },

        }
    }();
    initializing.init();
    binding.bindingevent();
    generalCls.fillPreReceiver();
    generalCls.fillPreSender();
    generalCls.fillBoxType(1);

    generalCls.fillStates();
    generalCls.fillStatesList();
    generalCls.fillgreadSelectedSenderfavorite();

    generalCls.fillgreadSelectedReciverfavorite();
    generalCls.fillgreadSelectedDriverfavorite();
    generalCls.fillgreadSelectedKalafavorite();

    generalCls.fillgreadSelectedPelakfavorite();
    generalCls.fillgreadSelectedLoadfavorite();
    /* generalCls.ConfigurationMap3();*/
    generalCls.fillgreadSelectedSenderAddressfavorite();
    generalCls.fillgreadSelectedReciverAddressfavorite();
    /* generalCls.ConfigurationMap();*/



    $('#s1, #s2, #s3, #s4, #s5, #s6, #s7, #s8,#s8,#s9').on('click', function () {
        if ($(this).index() <= $('.wizard .active').index()) {
            generalCls.Setwizard($(this).index() + 1);
            $("#DVRegisterBox").show();
            generalCls.SetWizard(1);
        }
    });
    /* FormShippingDocumentationSystemClick.GETUserFleetListTajmi();*/
    FormShippingDocumentationSystemClick.GetCostSettings();
    FormShippingDocumentationSystemClick.GetCostSettingsForTajmi();
    FormShippingDocumentationSystemClick.LoadingRouteMapNext();

    // $("#uc_load").append($(".uc").html());

    //print barname
    $(".btnPrint").on("click", function () {
        let DocId = objid;
        let printType = $(this).attr("key");
        $("#printId").val(DocId);
        $("#printType").val(printType);
        $("#frmPrint").submit();

    })

    $("#modalPrint").on("click", function () {

        $("#modalPrint").modal("hide")

    })
    $("#DNTCaptchaInputText").on("click", function () {

        $("#error-captxtDNT").addClass("d-none");
    });
    $("#CaptchaCode").on("click", function () {

        $("#error-CaptchaCode").addClass("d-none");
    });
};



