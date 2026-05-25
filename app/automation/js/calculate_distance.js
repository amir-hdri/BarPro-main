({ originLat, originLng, destLat, destLng }) => {
    return new Promise((resolve) => {
        // تلاش برای استفاده از ماتریس فاصله گوگل مپس
        if (typeof google !== 'undefined' && google.maps) {
            const service = new google.maps.DistanceMatrixService();
            service.getDistanceMatrix(
                {
                    origins: [{lat: originLat, lng: originLng}],
                    destinations: [{lat: destLat, lng: destLng}],
                    travelMode: google.maps.TravelMode.DRIVING,
                    unitSystem: google.maps.UnitSystem.METRIC
                },
                (response, status) => {
                    if (status === 'OK' && response.rows[0].elements[0].status === 'OK') {
                        const element = response.rows[0].elements[0];
                        resolve({
                            distance: element.distance.text,
                            distance_value: element.distance.value,
                            duration: element.duration.text,
                            duration_value: element.duration.value
                        });
                    } else {
                        resolve(null);
                    }
                }
            );
        } else {
            // روش جایگزین: فرمول هاورسین
            const R = 6371; // شعاع زمین به کیلومتر
            const dLat = (destLat - originLat) * Math.PI / 180;
            const dLon = (destLng - originLng) * Math.PI / 180;
            const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                      Math.cos(originLat * Math.PI / 180) *
                      Math.cos(destLat * Math.PI / 180) *
                      Math.sin(dLon/2) * Math.sin(dLon/2);
            const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
            const distance = R * c;

            // تخمین زمان (با فرض میانگین سرعت ۶۰ کیلومتر بر ساعت)
            const duration_hours = distance / 60;
            const duration_min = duration_hours * 60;

            resolve({
                distance: distance.toFixed(2) + ' km',
                distance_value: distance * 1000,
                duration: Math.round(duration_min) + ' mins',
                duration_value: duration_min * 60,
                method: 'haversine'
            });
        }
    });
}
