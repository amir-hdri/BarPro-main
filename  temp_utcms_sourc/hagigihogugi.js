// JQUERY
$(document).ready(function () {
    // Action next
    $('.btn-next').on('click', function () {

        for (var i = 0; i < 11; i++) {
            $("#pills-" + i).removeClass("active")
            $("#pills-" + i + "-tab").removeClass("active")
            $("#pills-" + i + "-tab").removeClass("passed-step")
            $("#pills-" + i + "-tab").children("div").children("div").children(".icon-check-circle").hide()
            $("#pills-" + i + "-tab").children("div").children("div").children(".icon-circle").hide()
            $("#pills-" + i + "-tab").children("div").children("div").children(".icon-pause-circle").hide()
            $("#pills-" + i).removeClass("show")
        }

        const n = $(this).attr('data-to').split("-")[1];
        for (var i = 0; i < n; i++) {
            $("#pills-" + i + "-tab").addClass("passed-step")
            $("#pills-" + i + "-tab").children("div").children("div").children(".icon-check-circle").show()
        }


        
        $("#pills-" + n).addClass("active")
        $("#pills-" + n + "-tab").addClass("active")
        $("#pills-" + n + "-tab").children("div").children("div").children(".icon-pause-circle").show()

        $("#pills-" + n).addClass("show")
        
        for (var i = n; i < 11; i++) {
            if (i != n) {
            $("#pills-" + i + "-tab").children("div").children("div").children(".icon-circle").show()
            }
        }

    });
    // Action back
    $('.btn-prev').on('click', function () {
        for (var i = 0; i < 11; i++) {
            $("#pills-" + i).removeClass("active")
            $("#pills-" + i + "-tab").removeClass("active")
            $("#pills-" + i + "-tab").removeClass("passed-step")
            $("#pills-" + i + "-tab").children("div").children("div").children(".icon-check-circle").hide()
            $("#pills-" + i + "-tab").children("div").children("div").children(".icon-circle").hide()
            $("#pills-" + i + "-tab").children("div").children("div").children(".icon-pause-circle").hide()
            $("#pills-" + i).removeClass("show")
        }

        const n = $(this).attr('data-to').split("-")[1];
        for (var i = 0; i < n; i++) {
            $("#pills-" + i + "-tab").addClass("passed-step")
            $("#pills-" + i + "-tab").children("div").children("div").children(".icon-check-circle").show()
        }



        $("#pills-" + n).addClass("active")
        $("#pills-" + n + "-tab").addClass("active")
        $("#pills-" + n + "-tab").children("div").children("div").children(".icon-pause-circle").show()

        $("#pills-" + n).addClass("show")

        for (var i = n; i < 11; i++) {
            if (i != n) {
                $("#pills-" + i + "-tab").children("div").children("div").children(".icon-circle").show()
            }
        }
    });


  

  
});