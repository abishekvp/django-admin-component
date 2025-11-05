// toastr.options = {
//     "progressBar": true,
//     "positionClass": "toast-top-center"
// }

$('#restartBtn').on('click', restartBot);
$('#stopBtn').on('click', stopBot);

function restartBot(){
    $.ajax({
        url: '/restart-bot',
        type: 'GET',
        success: function(response) {
            if (response && response.message) {
                if (response.status == 200) {
                    toastr.success(response.message);
                } else {
                    toastr.info(response.message)
                }
            }
        },
        error: function(xhr, status, error) {
            toastr.warning('Error restarting bot: ' + error);
        }
    });
}

function stopBot(){
    $.ajax({
        url: '/stop-bot',
        type: 'GET',
        success: function(response) {
            if (response && response.message) {
                if (response.status == 200) {
                    toastr.success(response.message);
                } else {
                    toastr.info(response.message)
                }
            }
        },
        error: function(xhr, status, error) {
            toastr.warning('Error restarting bot: ' + error);
        }
    });
}