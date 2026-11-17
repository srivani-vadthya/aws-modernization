module app {
    "use strict";
    imsApp.controller("ordersCtrl", ordersCtrl);
    ordersCtrl.$inject = ["$scope", "$resource"];

    function ordersCtrl($scope: any, $resource: any) {
        $scope.save = function (vm: any) {
            $resource(util.getPrePath() + '/api/OrdersApi').save(vm, function () { });
        };
        $scope.cancel = function (vm: any) {
            var resource = $resource(util.getPrePath() + '/api/OrdersApi/Cancel', null, {
                'cancel': { method: 'PATCH' }
            });
            resource.cancel(vm);
        };
        $scope.legacy = function () {
            $resource('/api/NoSuchApi').get({ id: 1 });
        };
    }
}
