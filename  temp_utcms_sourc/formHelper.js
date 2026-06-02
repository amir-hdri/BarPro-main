var formHelper = function () {
    var formValidate = false;

    function fillCombo(selectBox, controller, method) {

        webService.call({
            url: controller,
            function: method,
            success: function (result) {
                var options = '';

                //options += '<option value="" selected="selected">انتخاب کنید</option>';

                $(result).each(function () {
                    options += '<option value="' + this.key + '">' + this.value + '</option>';
                });

                selectBox.append(options);
                selectBox[0].selectedIndex = 0;
            },
            error: function (responseText) {
                msgModal.error(responseText, 'خطا');
            }
        });
    }

    function fillSubCombo(controller, val) {

        var Url = controller + "/fillComboByParent";

        $.ajax({
            url: Url,
            data: {
                key: val
            },
            cache: false,
            method: "POST",
            success: function (result) {
                var options = '<option value="" selected="selected"></option>';

                $(result).each(function () {
                    options += '<option value="' + this.key + '">' + this.val + '</option>';
                });

                selectBox.append(options);
                selectBox[0].selectedIndex = -1;
            },
            error: function (xmlHttpRequest, textStatus, errorThrown) {
                if (xmlHttpRequest.readyState == 0 || xmlHttpRequest.status == 0) {
                    return;
                } else {
                    msgModal.error(xmlHttpRequest.responseText, 'خطا');
                }
            }
        });
    }

    function _fillFormData(data, formId, callBack) {
        temp = $(data);
        var isAjaxStoped = false;
        $(document).ajaxStop(function () {
            isAjaxStoped = true;
        });
        check();
        function check() {
            setTimeout(function () {
                if (isAjaxStoped) {
                    fill();
                } else {
                    check();
                }
            });
        }
        function fill() {
            $(data).each(function () {
                var data = temp[0];

                for (var key in data) {
                    var entity = $("#" + formId + " *[name='" + key + "']");
                    if (entity[0] != undefined) {
                        var tagName = entity[0].tagName;
                        switch (tagName) {
                            case "INPUT":
                                var type = entity.attr("type");
                                switch (type) {
                                    case "checkbox":
                                        entity.prop('checked', data[key]);
                                        break;
                                    case "radio":
                                        entity.filter("[value='" + data[key] + "']").prop("checked", true).trigger('change');
                                        break;
                                    default:
                                        entity.val(data[key]).trigger('keydown');
                                }
                                break;
                            case "SELECT":
                                entity.val(data[key]).trigger('keydown').trigger("change");
                                break;
                            case "TEXTAREA":
                                entity.val(data[key]).trigger('keydown');
                                break;
                        }
                    }
                }

                if ($.type(callBack) === "function") {
                    callBack(data);
                }
            });
        }
    }

    function _addOrRemoveValidation(element, formId, status, validation) {
        try {
            if (status) {
                element.attr("data-fv-" + validation, true);
            }
            else {
                element.removeAttr("data-fv-" + validation);
            }
        } catch (e) {
            console.error(e);
        }
        _setOrRemoveElementToFormValidation(element, formId, status);
    }

    function _setOrRemoveElementToFormValidation(element, formId, status) {
        try {
            if (status) {
                element.attr("required", "required");
                formId.formValidation('addField', element);
            } else {
                element.removeAttr("required");
                formId.formValidation('addField', element);
                formId.formValidation('removeField', element);
            }
            element.parent().parent().removeClass("has-error has-success").find("small").css("display", "none");
        } catch (e) {
            console.error(e);
        }
    }

    return {
        init: function (formId) {

            $("#" + formId + " select.ajaxSelect").each(function () {
                var selectBox = $(this);

                var ajaxHandler = "/Handlers/" + selectBox.attr('data-handler') + ".ashx";
                var ajaxMethod = selectBox.attr('data-function');
                var ajaxParent = selectBox.attr('ajax-parent');

                if (ajaxHandler == undefined) {
                    return false;
                }

                if (ajaxMethod == undefined) {
                    return false;
                }

                if (ajaxParent == undefined) {
                    fillCombo(selectBox, ajaxHandler, ajaxMethod);
                } else {
                    var parentCombo = $("#" + formId + " select.ajaxSelect[name='" + ajaxParent + "']");

                    parentCombo.on('change', function () {
                        var parentComboVal = parentCombo.val();

                        if (parentComboVal == undefined || parentComboVal == '') {
                            return false;
                        } else {
                            fillSubCombo(parentComboVal);
                        }
                    });
                }
            });

            //===============================================================================

            //===============================================================================

            $('#' + formId).formValidation({
                framework: 'bootstrap',
                excluded: ':disabled',
                trigger: "keyup change", /*keydown*/
                icon: {
                    valid: '',
                    invalid: '',
                    validating: 'glyphicon glyphicon-refresh'
                }
            })
                .on('success.form.fv', function (e) {
                    formValidate = true;
                })
                .on('err.form.fv', function (e) {
                    formValidate = false;
                })
                .on('err.field.fv', function (e, data) {
                    formValidate = false;

                    // data.fv      --> The FormValidation instance
                    // data.field   --> The field name
                    // data.element --> The field element
                    //var tagName = data.element[0].tagName;
                    //switch (tagName) {
                    //    case "INPUT":
                    //        var type = data.element.attr("type");
                    //        switch (type) {
                    //            case "text":
                    //            case "hidden":
                    //            case "date":
                    //            case "password":
                    //                data.element.addClass("edited");
                    //                break;
                    //        }
                    //        break;
                    //    case "SELECT":
                    //        data.element.addClass("edited");
                    //        break;
                    //}
                });
        },

        /////////////////////////////////////////////////////////////////////////////////////

        clear: function (formId) {
            $("#" + formId + " *[name!='_key']").each(function () {
                var entity = $(this);

                var tagName = entity[0].tagName;
                if (tagName == "INPUT") {
                    var type = entity.attr("type");
                    if (type == "text" || type == "hidden") {
                        entity.val("");
                    }
                    if (type == "checkbox") {
                        entity.prop('checked', false);
                    }
                }
                if (tagName == "SELECT") {
                    entity.val(-1);
                }
            });

            $("#" + formId).data('formValidation').resetForm();
        },

        /////////////////////////////////////////////////////////////////////////////////////

        validate: {
            init: function (formId) {
                $('#' + formId).formValidation('validate');
                return this;
            },
            success: function (success) {
                if (success == undefined) {
                    success = function (result) { };
                }
                if (formValidate)
                    success();
                return this;
            },
            error: function (error) {
                console.log("error0:", error);
                if (error == undefined) {
                    error = function (error) { console.log("error1:", error); };
                }
                if (!formValidate) {
                    error();
                    console.log("error2:", error);
                }
                return this;
            }
        },

        /////////////////////////////////////////////////////////////////////////////////////

        fill: {
            objSuccess: null,
            objError: null,
            init: function (route, formId, key, method) {
                //key = key || null;

                if (key == null) {
                    console.info("key is null");

                    return false;
                }

                method = method || "getFormData";

                var waitForSet = function () {
                    setTimeout(function () {
                        if (this.objSuccess !== undefined) {
                            callWebService()
                        } else {
                            waitForSet();
                        }
                    }, 200);
                }

                var callWebService = function () {
                    objData = webService.call({
                        url: route,
                        function: method,
                        data: { key: key },
                        success: function (result) {
                            objSuccess(result, formId);
                        },
                        error: objError
                    });
                }

                waitForSet();

                return this;
            },
            success: function (success) {
                if (success == undefined) {
                    success = function (result) { };
                }
                objSuccess = function (result, formId) {
                    _fillFormData(result, formId, success);
                };

                return this;
            },
            error: function (error) {
                if (error == undefined) {
                    error = function (error) { };
                }
                objError = error;
                return this;
            }
        },

        /////////////////////////////////////////////////////////////////////////////////////

        submit: {
            objSuccess: null,
            objError: null,

            init: function (route, formId, key, createMethod, updateMethod) {
                key = key || null;
                createMethod = createMethod || "Create";
                updateMethod = updateMethod || "Update";

                var method = null;
                if (key == null) {
                    method = createMethod;
                } else {
                    method = updateMethod;
                }

                var form = $("#" + formId);

                var waitForSet = function () {
                    setTimeout(function () {
                        if (this.objSuccess !== undefined) {
                            callWebService()
                        } else {
                            waitForSet();
                        }
                    }, 200);
                }

                var callWebService = function () {
                    webService.call({
                        url: route,
                        function: method,
                        data: form,
                        success: objSuccess,
                        error: objError
                    });
                }

                waitForSet();

                return this;
            },
            success: function (success) {
                if (success == undefined) {
                    success = function (result) { };
                }
                objSuccess = success;
                return this;
            },
            error: function (error) {
                if (error == undefined) {
                    error = function (error) { };
                }
                objError = error;
                return this;
            }
        },

        /////////////////////////////////////////////////////////////////////////////////////

        delete: {
            objSuccess: null,
            objError: null,

            init: function (route, key, deleteMethod) {

                method = deleteMethod || "Delete";

                var waitForSet = function () {
                    setTimeout(function () {
                        if (this.objSuccess !== undefined) {
                            callWebService()
                        } else {
                            waitForSet();
                        }
                    }, 200);
                }

                var callWebService = function () {
                    webService.call({
                        url: route,
                        function: method,
                        data: { key: key },
                        success: objSuccess,
                        error: objError
                    });
                }

                waitForSet();

                return this;
            },
            success: function (success) {
                objSuccess = success;
                return this;
            },
            error: function (error) {
                objError = error;
                return this;
            }
        },

        getQueryString: function (name, url) {
            if (!url) url = window.location.href;
            name = name.replace(/[\[\]]/g, "\\$&");
            var regex = new RegExp("[?&]" + name + "(=([^&#]*)|&|#|$)"),
                results = regex.exec(url);
            if (!results) return null;
            if (!results[2]) return '';
            return decodeURIComponent(results[2].replace(/\+/g, " "));
        },

        fillFormData: function (data, formId, callBack) {
            _fillFormData(data, formId, callBack);
        },

        /*
         * اگر بخواهیم ولیدیشن خاصی را اعمال کنیم از این متد استفاده خواهیم کرد
         * status : For Add This Validation to element Send true else Send false.
         * validation : validation name for example >> "postalcode"
         */
        addOrRemoveValidation: function (element, formId, status, validation) {
            _addOrRemoveValidation(element, formId, status, validation);
        },

        /*
         * اگر بخواهیم ولیدیشن را از المنت برداریم یا به اضافه کنیم از این متد استفاده خواهیم کرد
         * element : نام فیلد مورد نظر مثل $("#form select[name='city']")
         * formId : for example >> $("#frmWiz1")
         * status : trtue >> اگر بخواهیم این المنت ولیدیشن داشته باشد
         * status : false >> اگر بخواهیم ولیدیشن المنت برداشته شود
         */
        setOrRemoveElementToFormValidation: function (element, formId, status) {
            _setOrRemoveElementToFormValidation(element, formId, status);
        },

        resetForm: function (formId) {
            try {
                document.getElementById(formId).reset();
                $("#" + formId + " *[name!='_key']").each(function () {
                    var entity = $(this);

                    var tagName = entity[0].tagName;
                    if (tagName == "INPUT") {
                        var type = entity.attr("type");
                        if (type == "text" || type == "hidden") {
                            entity.val("");
                        }
                        if (type == "checkbox") {
                            entity.prop('checked', false);
                        }
                    }
                    if (tagName == "SELECT") {
                        entity.val("");
                    }

                    if ($(this).is("data-fv-*")) {
                        _setOrRemoveElementToFormValidation($(this), $("#" + formId), false);
                    }
                });
                $("#" + formId).formValidation("resetForm", true);
            } catch (e) {
                console.log(e);
            }
        }

    };
};