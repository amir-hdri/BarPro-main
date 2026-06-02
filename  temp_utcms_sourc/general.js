var generalJS = function () {

    function _convertDivToModal() {
        //$.get("/Templates/modal-template.html", function (result) {
        //    var boxs = $(".modal-box");
        //    $.each(boxs, function () {
        //        var box = $(this);
        //        box.removeClass("modal-box");
        //        var classes = box.attr("class");
        //        box.attr("class", "");

        //        var modalTemplate = $(result).clone();
        //        var modalID = box.attr("id");
        //        var modalTitle = box.attr("title");

        //        box.attr("id", "");
        //        box.attr("title", "");

        //        modalTemplate.attr("id", modalID);
        //        modalTemplate.find("div.modal-dialog").addClass(classes);
        //        modalTemplate.find(".modal-title").text(modalTitle);
        //        modalTemplate.appendTo(box.parent());

        //        box.appendTo(modalTemplate.find("div.modal-body"));
        //    });
        //});
    }

    //============================================================================

    function _setFileInputMethods() {
        var fileInputs = $(".file-input");

        $.each(fileInputs, function () {
            var fileInput = $(this);
            fileInput.off("change");
            fileInput.on("change", function () { _onChangeFileInput(this) });
        });
    }

    //============================================================================

    function _onChangeFileInput(e) {
        var fileInput = $(e);
        var container = fileInput.closest("div.form-group");
        var pathInput = container.find("input[name='selectedFilePath']");
        if (pathInput !== undefined) {
            pathInput.val(fileInput.val());
        }

        var image = container.find("img");
        if (image !== undefined) {
            var fileInputTag = fileInput[0];
            if (fileInputTag) {
                var reader = new FileReader();
                reader.onload = function (e) {
                    image.prop('src', e.target.result);
                };
                reader.readAsDataURL(fileInputTag.files[0]);
            }
        }
    }

    //============================================================================

    function _setDatePickers() {
        $(".persianDatePicker").each(function () {
            $(this).persianDatepicker({
                format: 'YYYY/MM/DD',
                autoClose: true,
                onSelect: function () {
                }
            });
            $(this).val('');
        });

        $(".persianDatePicker").on('keydown', function () {
            return false;
        });

        $(".gregorianDatePicker").each(function () {
            $(this).datepicker({
                format: "yyyy/mm/dd",
                todayBtn: true,
                forceParse: false,
                autoclose: true,
                todayHighlight: true,
                rtl: true
            });
            $(this).val('');
        });

        $(".gregorianDatePicker").on('keydown', function () {
            return false;
        });
    }

    //============================================================================

    function _setTooltips() {
        $("[data-toggle=tooltip]")
            .tooltip({
                html: true
            });
    }

    //============================================================================

    function _setSelect2s() {
        //$(".select2").select2();
    }

    //============================================================================

    function _getQueryString(name, url) {
        if (!url) url = window.location.href;
        name = name.replace(/[\[\]]/g, "\\$&");
        var regex = new RegExp("[?&]" + name + "(=([^&#]*)|&|#|$)"),
            results = regex.exec(url);
        if (!results) return null;
        if (!results[2]) return '';
        return decodeURIComponent(results[2].replace(/\+/g, " "));
    };

    //============================================================================

    function _checkAjaxRequestResult() {
        $(document).ajaxComplete(function (event, request, settings) {
            if (request.responseText === "Session Time Out") {
                location.href = "/login.aspx";
            }
        });
    }

    //============================================================================

    function _setSession(sessionName, sessionValue) {
        $.ajax({
            type: "POST",
            url: "/Handlers/GeneralHandler.ashx",
            data: { "function": "SetSession", sessionName: sessionName, sessionValue: sessionValue },
            async: false,
            success: function (result) {
                sessionValue = result;
            },
            error: function (xmlHttpRequest, textStatus, thrownError) {
                msgModal.error(xmlHttpRequest.responseText, 'خطا');
            }
        });
    }

    function _getSession(sessionName) {
        var sessionValue = null;

        $.ajax({
            type: "POST",
            //url: "/Handlers/GeneralHandler.ashx",
            url: "/Account/FormDocumentDetailsRegister.aspx",
            data: { "function": "GetSession", sessionName: sessionName },
            async: false,
            success: function (result) {
                sessionValue = result;
            },
            error: function (xmlHttpRequest, textStatus, thrownError) {
                msgModal.error(xmlHttpRequest.responseText, 'خطا');
            }
        });

        return sessionValue;
    };
    function _getUserInfoSession() {
        var sessionValue = null;

        $.ajax({
            type: "POST",
            //url: "/Handlers/GeneralHandler.ashx",
            url: "/Account/FormDocumentDetailsRegister.aspx",
            data: { "function": "GetUserInfo" },
            async: false,
            success: function (result) {
                sessionValue = result;
            },
            error: function (xmlHttpRequest, textStatus, thrownError) {
                msgModal.error(xmlHttpRequest.responseText, 'خطا');
            }
        });

        return sessionValue;
    };

    function _removeSession(sessionName) {
        $.ajax({
            type: "POST",
            url: "/Handlers/GeneralHandler.ashx",
            data: { "function": "RemoveSession", sessionName: sessionName },
            async: false,
            success: function (result) {
            },
            error: function (xmlHttpRequest, textStatus, thrownError) {
                msgModal.error(xmlHttpRequest.responseText, 'خطا');
            }
        });
    };
    function _chekCaptcha(id, value) {
        var captchaIsTrue = null;
        $.ajax({
            type: "POST",
            url: "/Handlers/GeneralHandler.ashx",
            data: { "function": "checkCaptcha", id: id, value: value },
            async: false,
            success: function (result) {
                captchaIsTrue = result;
                console.log(result);
            },
            error: function (xmlHttpRequest, textStatus, thrownError) {
                msgModal.error(xmlHttpRequest.responseText, 'کد امنیتی');
            }
        });

        return captchaIsTrue;
    }


   function GetPelakChar(CharId) {
        switch (CharId) {
            case 1:
                return "الف";
            case 2:
                return "ب";
            case 3:
                return "پ";
            case 4:
                return "ت";
            case 5:
                return "ث";
            case 6:
                return "ج";
            case 7:
                return "چ";
            case 8:
                return "ح";
            case 9:
                return "خ";
            case 10:
                return "د";
            case 11:
                return "ذ";
            case 12:
                return "ر";
            case 13:
                return "ز";
            case 14:
                return "ژ";
            case 15:
                return "س";
            case 16:
                return "ش";
            case 17:
                return "ص";
            case 18:
                return "ض";
            case 19:
                return "ط";
            case 20:
                return "ظ";
            case 21:
                return "ع";
            case 22:
                return "غ";
            case 23:
                return "ف";
            case 24:
                return "ق";
            case 25:
                return "ک";
            case 26:
                return "گ";
            case 27:
                return "ل";
            case 28:
                return "م";
            case 29:
                return "ن";
            case 30:
                return "و";
            case 31:
                return "ه";
            case 32:
                return "ی";
            default:
                return "";
        }
    }


    //============================================================================

   function getFreeZoneCityName(FreeZoneId) {
        if (FreeZoneId == 1) {
            return "اروند";
        }
        else if (FreeZoneId == 2) {
            return "انزلی";
        }
        else if (FreeZoneId == 3) {
            return "چابهار";
        }
        else if (FreeZoneId == 4) {
            return "قشم";
        }
        else if (FreeZoneId == 5) {
            return "کیش";
        }
        else if (FreeZoneId == 6) {
            return "ماکو";
        }
        else if (FreeZoneId == 7) {
            return "ارس";
        }
    }

        //============================================================================

    //============================================================================
    return {
        initPageElements: function () {
            _convertDivToModal();
            //----------------------------------------------------------------------------
            _setFileInputMethods();
            //----------------------------------------------------------------------------
            _setDatePickers();
            //----------------------------------------------------------------------------
            //_setTooltips();
            //----------------------------------------------------------------------------
            _setSelect2s();
            //----------------------------------------------------------------------------
            _checkAjaxRequestResult();
        },

        //============================================================================

        setFileInputs: function () {
            _setFileInputMethods();
        },

        //============================================================================

        getQueryString: function (name, url) {
            return _getQueryString(name, url);
        },

        //============================================================================


        setSession: function (sessionName, sessionValue) {
            return _setSession(sessionName, sessionValue);
        },

        getSession: function (sessionName) {
            var sessionValue = _getSession(sessionName);
           
            return sessionValue;
        },

        getUserInfo: function () {
            var sessionValue = _getUserInfoSession();
            
            return sessionValue;
        },

        removeSession: function (sessionName) {
            return _removeSession(sessionName);
        },
        chekCaptcha: function (id, value) {
            return _chekCaptcha(id, value);
        },
        getFreeZoneCityName: function (FreeZoneId) {
            return getFreeZoneCityName(FreeZoneId);
        },
        GetPelakChar: function (CharId) {
            return GetPelakChar(CharId);
        }

    }
}();